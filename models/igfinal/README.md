# IGfinal_py: Investment Game toolkit in Python (IIM 2026/27, case 1)

Python version of `../IGfinal`. Same plan, same method, same inputs and outputs; only the language changed. `crosscheck.py` compares the two on the same prices.

**Plan:** we start 1.88% behind max(0, S&P 500). 30% of the portfolio goes into AI / IPO-related names (AMD, ASML, MSFT, GOOGL, AMZN, META, PLTR, BABA) and 70% into the replica from the team's replica study: the 50 largest S&P 500 companies without NVIDIA, at index weights. Once the book is 0.5% ahead, or on the IPO date, the sleeve is sold for good and the book holds the same 50 names at minimum-tracking-error weights. A cash rule picks the equity exposure.

Start with `Investment_Game_Guide.html`.

## Which Python

The scripts need numpy, pandas, scipy, matplotlib and yfinance (`requirements.txt`). On this Mac `/usr/local/bin/python3` (3.12) has them. The default `python3` on the PATH is a conda install without them, so either call the full path or install the requirements there.

## Routine

1. Copy your MarketWatch positions into `input/holdings.csv` (start from `holdings_template.csv`): `ticker,shares`, one `CASH` row.
2. `/usr/local/bin/python3 run_dashboard.py` (about 15 seconds).
3. Open `output/<date>/dashboard.html`: constraints first, then the exposure and the trade list.
4. Trade, update `holdings.csv`, run again so the trades are logged.

```
/usr/local/bin/python3 run_dashboard.py live      # Yahoo, up to the last close; saves data/snapshots/prices_<date>.csv
/usr/local/bin/python3 run_dashboard.py frozen    # rebuilds from the latest snapshot (or FROZEN_FILE in config.py)
/usr/local/bin/python3 validate.py frozen         # out-of-sample tests -> output/validation/
/usr/local/bin/python3 crosscheck.py              # R vs Python on the same date
```

## Files

| File | Role | R counterpart |
|---|---|---|
| `config.py` | Every assumption | `config.R` |
| `run_dashboard.py` | The run: constraints, bonus probability, trades, risk, allocation, stress, logs, website files | `run_dashboard.R` |
| `lib.py` | Risk measures, Euler and exact Shapley, replica weights, sleeve, bonus simulator | `R/lib.R` |
| `data.py` | Price layer with the frozen / live switch | `R/data.R` |
| `html_kit.py` | HTML helpers for the dashboard | `R/html.R` |
| `validate.py` | Replica, risk-model and simulator tests | `validate.R` |
| `crosscheck.py` | Compares this folder's output with `../IGfinal/output` | - |
| `input/`, `output/`, `state/`, `site_export/` | Same layout and file formats as the R version | |

## How close the two versions are

On the 13 Nov snapshot, target weights, share counts, every risk measure, Euler and Shapley contributions, stress results and all validation tables are identical (differences below 1e-8). Two things differ by design:

- **Random numbers.** The bonus simulation and the bootstrap intervals draw different random numbers in each language. The bonus probability differs by about half a point (23.8% here, 23.2% in R); intervals differ in the second decimal.
- **Optimiser.** The minimum-tracking-error weights use `scipy.optimize` (SLSQP) here and `quadprog` in R. The resulting weights agree to the printed precision.

Use one version for the live game, not both: each keeps its own `state/` and logs, and mixing them would split the transaction trail.

## Data note

Yahoo's `^VIX` series includes rows for days the stock market was closed. Both versions now keep only days on which the S&P 500 traded. Before this fix the R version carried about 90 such days as zero-return days, which shifted the risk figures slightly (5-day ES 11.82% before, 11.86% after).
