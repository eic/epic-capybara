import re

import awkward as ak
import click
import numpy as np
import uproot
from bokeh.layouts import gridplot
from bokeh.models import TabPanel, Tabs
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
def bara(files, match, unmatch):
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

    for key in keys:
        xmin = min(filter(
            lambda v: v is not None,
            map(ak.min, arr[key].values())
        ), default=None)
        xmax = max(filter(
            lambda v: v is not None,
            map(ak.max, arr[key].values())
        ), default=None)

        if xmin is None:
            continue
        xmax += 1

        nbins = 10
        if ("* uint" in str(ak.type(arr[key][_file]))
           or "* int" in str(ak.type(arr[key][_file]))):
            nbins = int(min(100, np.ceil(xmax - xmin)))

        it = iter(arr[key].items())
        file_ref, file_arr_ref = next(it)
        for _file, file_arr in it:
            if ((ak.num(file_arr, axis=0) != ak.num(file_arr_ref, axis=0))
               or ak.any(ak.num(file_arr, axis=1)
                         != ak.num(file_arr_ref, axis=1))
               or ak.any(ak.nan_to_none(file_arr)
                         != ak.nan_to_none(file_arr_ref))):
                fig = figure(x_axis_label=key, y_axis_label="Entries")
                collection_figs.setdefault(key.split("/")[0], []).append(fig)

                print(key)
                h = (
                    Hist.new
                    .Reg(nbins, xmin, xmax, name="x", label=key)
                    .Int64()
                )
                h.fill(x=ak.flatten(file_arr_ref))

                ys, edges = h.to_numpy()
                fig.step(edges, np.concatenate([ys, [ys[-1]]]), mode="after", legend_label="Reference", line_width=2, line_color="green")

                print("\t", file_ref.name)
                print(h)

                h = (
                    Hist.new
                    .Reg(nbins, xmin, xmax, name="x", label=key)
                    .Int64()
                )
                h.fill(x=ak.flatten(file_arr))

                ys, edges = h.to_numpy()
                fig.step(edges, np.concatenate([ys, [ys[-1]]]), mode="after", legend_label="New", line_color="red")

                print("\t", _file.name)
                print(h)

                print(file_arr, file_arr_ref)
            file_arr_ref = file_arr

    def to_filename(branch_name):
        return branch_name.replace("#", "__pound__")
    menu = []
    for collection_name, figs in collection_figs.items():
        menu.append((collection_name, to_filename(collection_name)))

    from bokeh.models import CustomJS, Dropdown
    def mk_dropdown(label="Select branch"):
        dropdown = Dropdown(label=label, menu=menu, width=350, button_type="primary")
        dropdown.js_on_event("menu_item_click", CustomJS(code="""
          console.log('dropdown: ' + this.item, this.toString())
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

    output_file(filename="capybara-reports/index.html", title="ePIC capybara report")
    save(mk_dropdown())
