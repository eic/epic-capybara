# epic-capybara

epic-capybara is a collection of tools for comparison and presentation of
differences between [ROOT](https://root.cern) TTree files. The available tools
are:

- `capybara capy` fetches CI artifacts either for a single revision of for the PR branch and its reference branch
- `capybara bara` projects each TTree leaf onto a histogram, render it as an html report using Bokeh
- `capybara cate` upload report to a github repo

See `capybara --help` or `capybara <tool-name> --help` for options.

### Installing

You will need to obtain epic-capybara itself and [Hatch](https://hatch.pypa.io/latest/).

```
git clone git@github.com:eic/epic-capybara.git
pip install hatch
cd epic-capybara
```

You can then either run the development version:
```
hatch env run -- capybara capy pr 123
```

Or build a wheel and install it locally
```
hatch build
pip install dist/*.whl
```

### Legacy scripts

This repository contains scripts for ROOT file comparisons in CI.
- `capy.py`: obtain ROOT files from previous CI pipelines
- `bara.py`: compare two ROOT files
