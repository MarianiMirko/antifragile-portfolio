# Team models

Put a Python file in this folder and it runs automatically every time prices are updated.
Its results appear on the Risk page under "Team models".

A model is a file with one function:

```python
def run(ctx):
    return {
        "title": "My model",
        "author": "Lorenzo",
        "description": "One or two sentences on what it measures.",
        "metrics": [
            {"name": "Signal", "value": "Risk-on", "signal": "normal", "comment": "optional"}
        ],
        "table": {
            "columns": ["Ticker", "Score"],
            "rows": [["NVDA", {"v": "0.82", "signal": "alert"}], ["PG", "0.10"]]
        }
    }
```

`signal` is `normal`, `caution` or `alert` and controls the highlighting on the site.
A table cell is either a plain value or `{"v": value, "signal": ...}` to highlight it.

What is inside `ctx`:

| Key | Content |
|---|---|
| `daily` | pandas DataFrame of one year of daily closing prices, one column per ticker (may be `None` if prices are unavailable) |
| `positions` | list of positions with `ticker`, `shares`, `price`, `value`, `weight`, `sector`, ... |
| `weights` | `{ticker: weight}` |
| `nav`, `cash` | fund value and cash in USD |
| `benchmark` | benchmark ticker (its prices are in `daily`) |
| `config`, `rules` | the contents of `config/fund.json` and `config/rules.json` |

Extra Python packages go in `requirements.txt`. Files whose name starts with `_` are ignored.
If a model crashes, the site shows the error for that model and everything else still updates.
