import re

import awkward as ak
import click
import numpy as np
import uproot
from bokeh.events import DocumentReady
from bokeh.io import curdoc
from bokeh.layouts import gridplot
from bokeh.plotting import figure, output_file, save
from hist import Hist


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
            and key.find("/") != -1
            and match_filter(key, match, unmatch)
        ]
        for key in keys:
            arr.setdefault(key, {})[_file] = tree[key].array()

    collection_figs = {}
    collection_with_diffs = set()

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

        xmax = x_min + x_range

        nbins = 10
        if (any("* uint" in str(ak.type(a)) for a in arr[key].values())
           or any("* int" in str(ak.type(a)) for a in arr[key].values())):
            nbins = int(min(100, np.ceil(x_range)))

        fig = figure(x_axis_label=key.split("/", 1)[1], y_axis_label="Entries")
        collection_figs.setdefault(key.split("/")[0], []).append(fig)

        prev_file_arr = None
        for (_file, file_arr), color, line_width in zip(arr[key].items(), ["green", "red"], [3, 2]):
            h = (
                Hist.new
                .Reg(nbins, 0, x_range, name="x", label=key)
                .Int64()
            )
            h.fill(x=ak.flatten(file_arr - x_min))

            ys, edges = h.to_numpy()
            fig.step(edges + x_min, np.concatenate([ys, [ys[-1]]]), mode="after", legend_label=_file.name, line_color=color, line_width=line_width)

            if prev_file_arr is not None:
                if ((ak.num(file_arr, axis=0) != ak.num(prev_file_arr, axis=0))
                   or ak.any(ak.num(file_arr, axis=1)
                             != ak.num(prev_file_arr, axis=1))
                   or ak.any(ak.nan_to_none(file_arr)
                             != ak.nan_to_none(prev_file_arr))):
                    print(key)
                    print(prev_file_arr, file_arr)
                    collection_with_diffs.add(key.split("/")[0])
            prev_file_arr = file_arr

    def to_filename(branch_name):
        return branch_name.replace("#", "__pound__")
    menu = []
    for collection_name, figs in collection_figs.items():
        if collection_name in collection_with_diffs:
            menu.append((collection_name + " (*)", to_filename(collection_name)))
    menu.append(None)
    for collection_name, figs in collection_figs.items():
        if collection_name not in collection_with_diffs:
            menu.append((collection_name, to_filename(collection_name)))

    from bokeh.models import CustomJS, Dropdown
    def mk_dropdown(label="Select branch"):
        dropdown = Dropdown(label=label, menu=menu, width=350, button_type="primary")
        dropdown.js_on_event("menu_item_click", CustomJS(code="""
          console.log('dropdown: ' + this.item, this.toString())
          window.location.hash = "#" + this.item;
          fetch(this.item + '.json')
            .then(function(response) { return response.json(); })
            .then(function(item) { Bokeh.documents[0].replace_with_json(item.doc); })
        """))
        return dropdown

    from bokeh.layouts import column
    from bokeh.embed import json_item
    import json
    for collection_name, figs in collection_figs.items():
        item = column(
          mk_dropdown(collection_name),
          gridplot(figs, ncols=3, width=400, height=300),
        )

        with open(f"capybara-reports/{to_filename(collection_name)}.json", "w") as fp:
            json.dump(json_item(item), fp)

    curdoc().js_on_event(DocumentReady, CustomJS(code="""
      var location = window.location.hash.replace(/^#/, "");
      if ((location != "") && ((typeof current_location === 'undefined') || (current_location != location))) {
        fetch(location + '.json')
            .then(function(response) { return response.json(); })
            .then(function(item) { Bokeh.documents[0].replace_with_json(item.doc); })
        window.current_location = location;
      }
    """))
    output_file(filename="capybara-reports/index.html", title="ePIC capybara report")
    save(mk_dropdown())

    if serve:
        import os
        os.chdir("capybara-reports/")
        from http.server import SimpleHTTPRequestHandler
        from socketserver import TCPServer
        with TCPServer(("127.0.0.1", 24535), SimpleHTTPRequestHandler) as httpd:
            print("Serving report at http://127.0.0.1:24535")
            try:
                httpd.serve_forever()
            except KeyboardInterrupt:
                pass
