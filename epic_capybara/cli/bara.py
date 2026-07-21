import gzip
import os
import re

import awkward as ak
import click
import numpy as np
import uproot
from bokeh.events import DocumentReady
from bokeh.io import curdoc
from bokeh.layouts import gridplot
from bokeh.models import ColumnDataSource
from bokeh.models import CustomJSExpr
from bokeh.models import Range1d
from bokeh.models import PrintfTickFormatter
from bokeh.plotting import figure, output_file, save
from hist import Hist
from scipy.stats import PermutationMethod, anderson_ksamp, kstest

from ..util import skip_common_prefix

# Cap Anderson-Darling sample size to keep runtime bounded on
# high-multiplicity collections.
_AD_MAX_N = 10_000


def _ad_rng(key):
    """Return a deterministic RNG seeded from the leaf key.

    Using a per-leaf seed (rather than a shared module-level RNG) makes each
    leaf's subsample independent of the number and order of previously
    processed leaves, so AD p-values stay reproducible when the set of
    processed collections changes (e.g. under different match/unmatch
    filters).
    """
    import hashlib
    digest = hashlib.blake2b(key.encode("utf-8"), digest_size=8).digest()
    return np.random.default_rng(int.from_bytes(digest, "little"))

_MIDPOINT_EXPR_CODE = """
const y1 = this.data.y1;
const y2 = this.data.y2;
return y1.map((v, i) => (v + y2[i]) / 2);
"""


def _is_leaf(obj):
    """Check if an uproot branch/field object is a leaf (has no sub-branches/sub-fields).

    Supports both TTree TBranch objects (which use `.branches`) and
    RNTuple RField objects (which use `.fields`).
    """
    if hasattr(obj, 'branches'):
        return len(obj.branches) == 0
    if hasattr(obj, 'fields'):
        return len(obj.fields) == 0
    return True


def _normalize_key(key):
    """Normalize uproot key format between TTree and RNTuple styles.

    TTree EDM4hep keys follow 'CollectionName/CollectionName.fieldPath' pattern.
    RNTuple EDM4hep keys follow 'CollectionName.fieldPath' pattern.
    This function converts TTree-style keys to the RNTuple-style format so that
    the same physics quantity has the same key regardless of the input file format.

    TTree keys for fixed-size array branches include a trailing '[N]' size
    annotation (e.g. 'covariance.covariance[21]') which is absent in RNTuple
    keys; this suffix is stripped so the two formats match.

    >>> _normalize_key('MCParticles/MCParticles.momentum.x')
    'MCParticles.momentum.x'
    >>> _normalize_key('MCParticles.momentum.x')
    'MCParticles.momentum.x'
    >>> _normalize_key('EventHeader/EventHeader.eventNumber')
    'EventHeader.eventNumber'
    >>> _normalize_key('CentralCKFTrackParameters/CentralCKFTrackParameters.covariance.covariance[21]')
    'CentralCKFTrackParameters.covariance.covariance'
    """
    if "/" in key:
        _, field_part = key.split("/", 1)
    else:
        field_part = key
    return re.sub(r'\[\d+\]$', '', field_part)


def match_filter(key, match, unmatch):
    accept = True
    if match:
        accept = False
        for regex in match:
            if regex.match(key):
                accept = True
    for regex in unmatch:
        if regex.match(key):
            accept = False
    return accept


@click.command()
@click.argument("files", type=click.File('rb'), nargs=-1)
@click.option(
    "-m", "--match", multiple=True,
    help="Only include collections with names matching a regex"
)
@click.option(
    "-M", "--unmatch", multiple=True,
    help="Exclude collections with names matching a regex"
)
@click.option(
    "--serve", is_flag=True,
    default=False,
    help="Run a local HTTP server to view the report"
)
def bara(files, match, unmatch, serve):
    arr = {}

    match = list(map(re.compile, match))
    unmatch = list(map(re.compile, unmatch))

    for _file in files:
        tree = uproot.open(_file)["events"]

        sort_by_evtnum = None
        for evtnum_key in ["EventHeader/EventHeader.eventNumber", "EventHeader.eventNumber"]:
            if evtnum_key in tree.keys(recursive=True):
                evtnum = tree[evtnum_key].array()
                sort_by_evtnum = ak.argsort(ak.flatten(evtnum))
                break

        for key in tree.keys(recursive=True):
            if not key.startswith("PARAMETERS") and _is_leaf(tree[key]):
                normalized = _normalize_key(key)
                if match_filter(normalized, match, unmatch):
                    val = tree[key].array()
                    if sort_by_evtnum is not None:
                        val = val[sort_by_evtnum]
                    arr.setdefault(normalized, {})[_file] = val

    paths = skip_common_prefix([_file.name.split("/") for _file in files])
    paths = skip_common_prefix([reversed(list(path)) for path in paths])
    labels = ["/".join(reversed(list(reversed_path))) for reversed_path in paths]

    collection_figs = {}
    collection_with_diffs = {}
    collection_ks_pvalue = {}
    collection_ad_pvalue = {}
    collection_matching_count = {}
    collection_step_exprs = {}

    for key in sorted(arr.keys()):
        if any("string" in str(ak.type(a)) for a in arr[key].values()):
            click.echo(f"String value detected for key \"{key}\". Skipping...")
            continue
        if any("bool" in str(ak.type(a)) for a in arr[key].values()):
            click.echo(f"Bool value detected for key \"{key}\". Skipping...")
            continue
        if any(a.layout.minmax_depth[0] < 2 for a in arr[key].values()):
            # Not possible for PODIO, here for general ROOT file support
            print(f"Skipping non-array branch \"{key}\"")
            continue

        x_min = min(filter(
            lambda v: v is not None,
            map(lambda a: ak.min(ak.mask(a, np.isfinite(a))), arr[key].values())
        ), default=None)
        if x_min is None:
            continue
        x_range = max(filter(
            lambda v: v is not None,
            map(lambda a: ak.max(ak.mask(a - x_min, np.isfinite(a))), arr[key].values())
        ), default=None)
        nbins = 10

        if (any("* uint" in str(ak.type(a)) for a in arr[key].values())
           or any("* int" in str(ak.type(a)) for a in arr[key].values())):
            x_range = x_range + 1
            nbins = int(min(100, np.ceil(x_range)))
        else:
            x_range = x_range * 1.1

        if x_range == 0:
            x_range = 1

        if "." in key:
            branch_name = key.split(".", 1)[0]
            leaf_name = key
        else:
            branch_name = key
            leaf_name = key

        midpoint_expr = collection_step_exprs.setdefault(
            branch_name,
            CustomJSExpr(code=_MIDPOINT_EXPR_CODE),
        )
        fig = figure(x_axis_label=leaf_name, y_axis_label="Entries")
        if x_range < 1.:
            fig.xaxis.formatter = PrintfTickFormatter(format="%.2g")
        collection_figs.setdefault(branch_name, []).append(fig)
        y_max = 0

        prev_file_arr = None
        vis_params = [
          ("green", 1.5, "solid", " "),
          ("red", 3, "dashed", ","),
          ("blue", 2, "dotted", "."),
        ]

        leaf_min_pvalue = 1.0
        if set(arr[key].keys()) != set(files):
            # not every file has the key
            collection_with_diffs[branch_name] = 0.0
            leaf_min_pvalue = 0.0

        for _file, label, (color, line_width, line_dash, hatch_pattern) in zip(files, labels, vis_params):
            if _file not in arr[key]:
                continue
            file_arr = arr[key][_file]

            # diff, KS and Anderson-Darling k-sample tests
            pvalue = None
            ks_pvalue = None
            ad_pvalue = None
            if prev_file_arr is not None:
                if ((ak.num(file_arr, axis=0) != ak.num(prev_file_arr, axis=0))
                   or ak.any(ak.num(file_arr, axis=1)
                             != ak.num(prev_file_arr, axis=1))
                   or ak.any(ak.nan_to_none(file_arr)
                             != ak.nan_to_none(prev_file_arr))):
                    if (ak.num(ak.flatten(file_arr, axis=None), axis=0) > 0 and
                        ak.num(ak.flatten(prev_file_arr, axis=None), axis=0) > 0):
                        # We can only apply the tests on non-empty arrays
                        flat_a = ak.to_numpy(ak.flatten(file_arr, axis=None))
                        flat_b = ak.to_numpy(ak.flatten(prev_file_arr, axis=None))
                        # Fast path: identical flattened contents
                        if (flat_a.shape == flat_b.shape
                                and np.array_equal(flat_a, flat_b)):
                            ks_pvalue = 1.0
                            ad_pvalue = 1.0
                        else:
                            ks_pvalue = kstest(flat_a, flat_b).pvalue
                            # AD cost grows ~linearly with sample size and
                            # dominates the total runtime for high-multiplicity
                            # collections. Subsample above _AD_MAX_N per side:
                            # AD at N=1e4 already resolves p-values well below
                            # any threshold we colour on, so larger samples buy
                            # no useful sensitivity.
                            rng = _ad_rng(key)
                            ad_a, ad_b = flat_a, flat_b
                            if len(ad_a) > _AD_MAX_N:
                                ad_a = rng.choice(ad_a, _AD_MAX_N, replace=False)
                            if len(ad_b) > _AD_MAX_N:
                                ad_b = rng.choice(ad_b, _AD_MAX_N, replace=False)
                            try:
                                # anderson_ksamp fails if all samples are
                                # identical or if there are too few distinct
                                # values.
                                ad_result = anderson_ksamp(
                                    [ad_a, ad_b],
                                    # n_resamples sets p-value resolution;
                                    # batch bounds peak memory (permutations
                                    # are otherwise materialized all at once,
                                    # which OOMs on large samples).
                                    # Seed the permutation RNG from the same
                                    # per-key stream used for subsampling so
                                    # the reported p-value is reproducible.
                                    method=PermutationMethod(n_resamples=999, batch=200, rng=rng),
                                    variant="midrank",
                                )
                                ad_pvalue = float(ad_result.pvalue)
                            except (ValueError, TypeError):
                                ad_pvalue = None
                        if ad_pvalue is None:
                            pvalue = ks_pvalue
                        else:
                            pvalue = min(ks_pvalue, ad_pvalue)
                    else:
                        ks_pvalue = 0
                        ad_pvalue = 0
                        pvalue = 0
                    print(key)
                    print(f"p_KS = {ks_pvalue:.3f}",
                          f"p_AD = {ad_pvalue:.3f}" if ad_pvalue is not None else "p_AD = n/a")
                    print(prev_file_arr)
                    print(file_arr)
                    collection_with_diffs[branch_name] = min(pvalue, collection_with_diffs.get(branch_name, 1.))
                    collection_ks_pvalue[branch_name] = min(ks_pvalue, collection_ks_pvalue.get(branch_name, 1.))
                    if ad_pvalue is not None:
                        collection_ad_pvalue[branch_name] = min(ad_pvalue, collection_ad_pvalue.get(branch_name, 1.))
                    leaf_min_pvalue = min(leaf_min_pvalue, pvalue)

            # Figure
            h = (
                Hist.new
                .Reg(nbins, 0, x_range, name="x", label=key)
                .Int64()
            )
            h.fill(x=ak.flatten(file_arr - x_min, axis=None))

            ys, edges = h.to_numpy()
            y0 = np.concatenate([ys, [ys[-1]]])
            legend_parts = [label]
            if ks_pvalue is not None:
                legend_parts.append(f"{100*ks_pvalue:.0f}%CL KS")
            if ad_pvalue is not None:
                legend_parts.append(f"{100*ad_pvalue:.0f}%CL AD")
            legend_label = "\n".join(legend_parts)
            source = ColumnDataSource(
                {
                    "x": edges + x_min,
                    "y1": y0 - np.sqrt(y0),
                    "y2": y0 + np.sqrt(y0),
                }
            )
            step_r = fig.step(
                x="x",
                y={"expr": midpoint_expr},
                mode="after",
                source=source,
                legend_label=legend_label,
                line_color=color,
                line_width=line_width,
                line_dash=line_dash,
            )
            step_r.nonselection_glyph = step_r.glyph
            varea_r = fig.varea_step(
                x="x",
                y1="y1",
                y2="y2",
                step_mode="after",
                source=source,
                legend_label=legend_label,
                fill_color=color if hatch_pattern == " " else None,
                fill_alpha=0.25,
                hatch_color=color,
                hatch_alpha=0.5,
                hatch_pattern=hatch_pattern,
            )
            varea_r.nonselection_glyph = varea_r.glyph
            fig.legend.background_fill_alpha = 0.5 # make legend more transparent

            y_max = max(y_max, np.max(y0 + np.sqrt(y0)))
            prev_file_arr = file_arr

        if leaf_min_pvalue == 1.0:
            collection_matching_count[branch_name] = collection_matching_count.get(branch_name, 0) + 1

        x_bounds = (x_min - 0.05 * x_range, x_min + 1.05 * x_range)
        y_bounds = (- 0.05 * y_max, 1.05 * y_max)
        # Set y range for histograms
        if np.all(np.isfinite(x_bounds)):
            try:
                fig.x_range = Range1d(
                    *x_bounds,
                    bounds=x_bounds)
            except ValueError as e:
                click.secho(str(e), fg="red", err=True)
        else:
            click.secho(f"overflow while calculating x bounds for \"{key}\"", fg="red", err=True)
        if np.all(np.isfinite(y_bounds)):
            try:
                fig.y_range = Range1d(
                    *y_bounds,
                    bounds=y_bounds)
            except ValueError as e:
                click.secho(str(e), fg="red", err=True)
        else:
            click.secho(f"overflow while calculating y bounds for \"{key}\"", fg="red", err=True)

    def to_filename(branch_name):
        return branch_name.replace("#", "__pound__").replace("/", "__underscore__")

    def option_key(item):
        collection_name, figs = item
        key = ""
        if collection_name in collection_with_diffs:
            if collection_with_diffs[collection_name] > 0.99:
                key += " 0.99"
            elif collection_with_diffs[collection_name] > 0.95:
                key += " 0.95"
            elif collection_with_diffs[collection_name] > 0.67:
                key += " 0.67"
            else:
                key += " 0.00"
        key += collection_name.lstrip("_")
        return key

    options = [("", "")]
    for collection_name, figs in sorted(collection_figs.items(), key=option_key):
        marker = ""
        if collection_name in collection_with_diffs:
            if collection_with_diffs[collection_name] > 0.99:
                marker = " (*)"
            elif collection_with_diffs[collection_name] > 0.95:
                marker = " (**)"
            elif collection_with_diffs[collection_name] > 0.67:
                marker = " (***)"
            else:
                marker = " (****)"
        options.append((to_filename(collection_name), collection_name + marker))

    from bokeh.models import CustomJS, Select, DataTable, TableColumn, HTMLTemplateFormatter, NumberFormatter, StringFormatter

    def mk_summary_table():
        rows = []
        for collection_name, figs in sorted(
            collection_figs.items(),
            key=lambda item: item[0].lstrip("_"),
        ):
            if collection_name in collection_with_diffs:
                pvalue = collection_with_diffs[collection_name]
                if pvalue > 0.99:
                    color = "#28a745"  # green
                elif pvalue > 0.95:
                    color = "#ffc107"  # yellow
                elif pvalue > 0.67:
                    color = "#fd7e14"  # orange
                else:
                    color = "#dc3545"  # red
                ks_str = (f"{collection_ks_pvalue[collection_name]:.3f}"
                          if collection_name in collection_ks_pvalue else "")
                ad_str = (f"{collection_ad_pvalue[collection_name]:.3f}"
                          if collection_name in collection_ad_pvalue else "n/a")
            else:
                color = "transparent"
                ks_str = ""
                ad_str = ""
            n_total = len(figs)
            n_match = collection_matching_count.get(collection_name, 0)
            n_diff = n_total - n_match
            rows.append((collection_name, color, ks_str, ad_str, n_match, n_diff, n_total))

        source = ColumnDataSource({
            "collection": [r[0] for r in rows],
            "filename":   [to_filename(r[0]) for r in rows],
            "color":      [r[1] for r in rows],
            "ks_pvalue":  [r[2] for r in rows],
            "ad_pvalue":  [r[3] for r in rows],
            "nmatch":     [r[4] for r in rows],
            "ndiff":      [r[5] for r in rows],
            "nplots":     [r[6] for r in rows],
        })
        square_style = (
            'display:inline-block;width:0.9em;height:0.9em;'
            'margin-right:6px;vertical-align:middle;'
            'border:1px solid #999;background-color:<%= color %>;'
        )
        link_fmt = HTMLTemplateFormatter(
            template=f'<span style="{square_style}"></span>'
                     '<a href="#<%= filename %>"><%= value %></a>'
        )
        right_str = StringFormatter(text_align="right")
        right_num = NumberFormatter(text_align="right")
        columns = [
            TableColumn(field="collection", title="Collection", formatter=link_fmt, width=500),
            TableColumn(field="ks_pvalue", title="min KS p-value", formatter=right_str, width=120),
            TableColumn(field="ad_pvalue", title="min AD p-value", formatter=right_str, width=120),
            TableColumn(field="nmatch", title="# matching", formatter=right_num, width=80),
            TableColumn(field="ndiff", title="# differing", formatter=right_num, width=80),
            TableColumn(field="nplots", title="# plots", formatter=right_num, width=80),
        ]
        table = DataTable(
            source=source,
            columns=columns,
            width=800,
            sizing_mode="stretch_height",
            index_position=None,
            sortable=True,
            selectable=True,
        )
        source.selected.js_on_change("indices", CustomJS(args={"source": source}, code="""
          const idx = cb_obj.indices;
          if (idx.length > 0) {
            const filename = source.data["filename"][idx[0]];
            window.location.hash = "#" + filename;
            fetchAndReplaceBokehDocument(filename);
          }
        """))
        return table

    def mk_dropdown(value=""):
        dropdown = Select(title="Select branch (**** < 67% CL, ..., * > 99% CL stat. equiv.):", value=value, options=options)
        dropdown.js_on_change("value", CustomJS(code="""
          console.log('dropdown: ' + this.value, this.toString())
          if (this.value != "") {
            window.location.hash = "#" + this.value;
            fetchAndReplaceBokehDocument(this.value);
          } else {
            // Empty option selected: navigate back to the index page.
            window.location.hash = "";
          }
        """))
        return dropdown

    def mk_dropdown_minimal(value=""):
        # Embed only the currently selected option; the full list is stored once
        # in index.html's JavaScript and restored client-side after each load.
        # This avoids repeating a ~54 KB options list in every .json.gz file.
        label = next((lbl for val, lbl in options if val == value), value)
        minimal_options = [("", "")] + ([(value, label)] if value else [])
        dropdown = Select(title="Select branch (**** < 67% CL, ..., * > 99% CL stat. equiv.):", value=value, options=minimal_options)
        dropdown.js_on_change("value", CustomJS(code="""
          console.log('dropdown: ' + this.value, this.toString())
          if (this.value != "") {
            window.location.hash = "#" + this.value;
            fetchAndReplaceBokehDocument(this.value);
          } else {
            // Empty option selected: navigate back to the index page.
            window.location.hash = "";
          }
        """))
        return dropdown

    from bokeh.layouts import column
    from bokeh.embed import json_item
    import json

    os.makedirs("capybara-reports", exist_ok=True)

    for collection_name, figs in collection_figs.items():
        item = column(
          mk_dropdown_minimal(collection_name),
          gridplot(figs, ncols=3, width=400, height=300),
        )

        with gzip.open(f"capybara-reports/{to_filename(collection_name)}.json.gz", "wt") as fp:
            json.dump(json_item(item), fp, separators=(',', ':'))

    curdoc().js_on_event(DocumentReady, CustomJS(args={"all_options": options}, code="""
      window._bokehSelectOptions = all_options;

      function fetchAndReplaceBokehDocument(location) {
        fetch(location + '.json.gz')
          .then(async function(response) {
            if (!response.ok) {
                throw new Error('Network response was not ok');
            }

            const ds = new DecompressionStream('gzip');
            const decompressedStream = response.body.pipeThrough(ds);
            const decompressedResponse = new Response(decompressedStream);
            const item = await decompressedResponse.json();

            Bokeh.documents[0].replace_with_json(item.doc);

            // Restore the full options list to the newly loaded Select widget.
            for (const [, model] of Bokeh.documents[0]._all_models) {
              if (model.options instanceof Array) {
                model.options = window._bokehSelectOptions;
                model.value = location;
                break;
              }
            }
          })
          .catch(function(error) {
            console.error('Fetch or decompression failed:', error);
          });
      }

      window.onhashchange = function() {
        var location = window.location.hash.replace(/^#/, "");
        if (location == "") {
          // No hash: return to the index page. Since there is no index.json.gz,
          // just reload the page to get a fresh index.html.
          if (typeof window.current_location !== 'undefined') {
            window.location.reload();
          }
          return;
        }
        if ((typeof current_location === 'undefined') || (current_location != location)) {
          fetchAndReplaceBokehDocument(location);
          window.current_location = location;
        }
      }
      window.onhashchange();
    """))
    output_file(filename="capybara-reports/index.html", title="ePIC capybara report")
    save(column(
        mk_dropdown(),
        mk_summary_table(),
        sizing_mode="stretch_height",
    ))

    if serve:
        os.chdir("capybara-reports/")
        from http.server import SimpleHTTPRequestHandler
        from socketserver import TCPServer
        with TCPServer(("127.0.0.1", 24535), SimpleHTTPRequestHandler) as httpd:
            print("Serving report at http://127.0.0.1:24535")
            try:
                httpd.serve_forever()
            except KeyboardInterrupt:
                pass
