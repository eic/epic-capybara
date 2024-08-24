import os
import re

import awkward as ak
import click
import numpy as np
import uproot
from bokeh.events import DocumentReady
from bokeh.io import curdoc
from bokeh.layouts import gridplot
from bokeh.models import Range1d
from bokeh.plotting import figure, output_file, save
from hist import Hist
from scipy.stats import kstest

from ..util import skip_common_prefix


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
        keys = [
            key for key in tree.keys(recursive=True)
            if not key.startswith("PARAMETERS")
            and len(tree[key].branches) == 0
            and match_filter(key, match, unmatch)
        ]
        for key in keys:
            arr.setdefault(key, {})[_file] = tree[key].array()

    paths = skip_common_prefix([_file.name.split("/") for _file in files])
    paths = skip_common_prefix([reversed(list(path)) for path in paths])
    labels = ["/".join(reversed(list(reversed_path))) for reversed_path in paths]

    collection_figs = {}
    collection_with_diffs = {}

    for key in sorted(arr.keys()):
        x_min = min(filter(
            lambda v: v is not None,
            map(lambda a: ak.min(ak.mask(a, np.isfinite(a))), arr[key].values())
        ), default=None)
        if x_min is None:
            continue
        x_range = max(filter(
            lambda v: v is not None,
            map(lambda a: ak.max(ak.mask(a - x_min, np.isfinite(a))), arr[key].values())
        ), default=None) + 1

        x_max = x_min + x_range

        nbins = 10
        if (any("* uint" in str(ak.type(a)) for a in arr[key].values())
           or any("* int" in str(ak.type(a)) for a in arr[key].values())):
            nbins = int(min(100, np.ceil(x_range)))

        if "/" in key:
            branch_name, leaf_name = key.split("/", 1)
        else:
            branch_name = key
            leaf_name = key

        fig = figure(x_axis_label=leaf_name, y_axis_label="Entries")
        collection_figs.setdefault(branch_name, []).append(fig)
        y_max = 0

        prev_file_arr = None
        vis_params = [
          ("green", 1.5, "solid"),
          ("red", 3, "dashed"),
          ("blue", 2, "dotted"),
        ]

        if set(arr[key].keys()) != set(files):
            # not every file has the key
            collection_with_diffs[branch_name] = 0.0

        for _file, label, (color, line_width, line_dash) in zip(files, labels, vis_params):
            if _file not in arr[key]:
                continue
            file_arr = arr[key][_file]
            h = (
                Hist.new
                .Reg(nbins, 0, x_range, name="x", label=key)
                .Int64()
            )
            h.fill(x=ak.flatten(file_arr - x_min, axis=None))

            ys, edges = h.to_numpy()
            fig.step(
                edges + x_min, np.concatenate([ys, [ys[-1]]]),
                mode="after",
                legend_label=label,
                line_color=color,
                line_width=line_width,
                line_dash=line_dash,
            )

            if prev_file_arr is not None:
                if ((ak.num(file_arr, axis=0) != ak.num(prev_file_arr, axis=0))
                   or ak.any(ak.num(file_arr, axis=1)
                             != ak.num(prev_file_arr, axis=1))
                   or ak.any(ak.nan_to_none(file_arr)
                             != ak.nan_to_none(prev_file_arr))):
                    if (ak.num(ak.flatten(file_arr, axis=None), axis=0) > 0 and
                        ak.num(ak.flatten(prev_file_arr, axis=None), axis=0) > 0):
                        # We can only apply the KS test on non-empty arrays
                        pvalue = kstest(
                                ak.to_numpy(ak.flatten(file_arr, axis=None)),
                                ak.to_numpy(ak.flatten(prev_file_arr, axis=None))
                            ).pvalue
                    else:
                        pvalue = 0
                    print(key)
                    print(prev_file_arr, file_arr, f"p = {pvalue:.3f}")
                    collection_with_diffs[branch_name] = pvalue

            y_max = max(y_max, np.max(y0 + np.sqrt(y0)))
            prev_file_arr = file_arr

        # Set y range for histograms
        fig.x_range = Range1d(
            x_min - 0.05 * (x_max - x_min), x_max + 0.05 * (x_max - x_min),
            bounds=(x_min - 0.05 * (x_max - x_min), x_max + 0.05 * (x_max - x_min)))
        fig.y_range = Range1d(
            - 0.05 * y_max, 1.05 * y_max,
            bounds=(- 0.05 * y_max, 1.05 * y_max))

    def to_filename(branch_name):
        return branch_name.replace("#", "__pound__")

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

    from bokeh.models import CustomJS, Select
    def mk_dropdown(value=""):
        dropdown = Select(title="Select branch (**** < 67% CL, ..., * > 99% CL stat. equiv.):", value=value, options=options)
        dropdown.js_on_change("value", CustomJS(code="""
          console.log('dropdown: ' + this.value, this.toString())
          if (this.value != "") {
            window.location.hash = "#" + this.value;
            fetch(this.value + '.json')
              .then(function(response) { return response.json(); })
              .then(function(item) { Bokeh.documents[0].replace_with_json(item.doc); })
          }
        """))
        return dropdown

    from bokeh.layouts import column
    from bokeh.embed import json_item
    import json

    os.makedirs("capybara-reports", exist_ok=True)

    for collection_name, figs in collection_figs.items():
        item = column(
          mk_dropdown(collection_name),
          gridplot(figs, ncols=3, width=400, height=300),
        )

        with open(f"capybara-reports/{to_filename(collection_name)}.json", "w") as fp:
            json.dump(json_item(item), fp)

    curdoc().js_on_event(DocumentReady, CustomJS(code="""
      window.onhashchange = function() {
        var location = window.location.hash.replace(/^#/, "");
        if ((location != "") && ((typeof current_location === 'undefined') || (current_location != location))) {
          fetch(location + '.json')
              .then(function(response) { return response.json(); })
              .then(function(item) { Bokeh.documents[0].replace_with_json(item.doc); })
          window.current_location = location;
        }
      }
      window.onhashchange();
    """))
    output_file(filename="capybara-reports/index.html", title="ePIC capybara report")
    save(mk_dropdown())

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
