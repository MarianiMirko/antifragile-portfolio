# Antifragile Portfolio: fund dashboard

The website of our simulated fund for the Investment Game of *Institutional Investment Management*
(MSc Finance, University of Groningen, 2026/27). It shows the fund value, positions, risk, our
limits and the alerts they generate.

Live site: https://antifragileportfolio.eu (GitHub Pages)

> **The site currently shows demo data.** `config/fund.json` has `"demo_mode": true`, so every page
> reads the invented portfolio in `data/demo/`. Set it to `false` to show the real fund.

## How it works

```
MarketWatch (login needed)          Yahoo Finance prices            The team
        |                                   |                          |
  Claude scheduled task               GitHub Action, hourly      edits files in content/
  reads positions + trades            scripts/update.py                |
        |                                   |                          |
  data/holdings.json  ───────────►  data/*.json  ◄─────────────────────┘
  data/transactions.json                    |
                                    static site (HTML + JS) reads the JSON
```

- **No server, no database.** The site is plain HTML, CSS and JavaScript. Charts load from a CDN
  (TradingView Lightweight Charts, Chart.js, Apache ECharts, marked).
- **Built to load fast.** Fonts are served from the site itself (`assets/fonts/`). Our own scripts run
  first and fetch the data while the chart libraries are still downloading, so the header and the
  figures do not wait for them; a page calls `await App.libs` just before the first thing that needs
  a library. ECharts, the largest file, loads in the background and its charts are drawn when it
  arrives (`assets/js/viz.js`). `config/fund.json` is kept for five minutes per browser tab, so a
  change to it can take a few minutes to show. The pages load our scripts and the stylesheet with a version
  number (`app.js?v=2`): **raise it in every page when a script or the stylesheet changes in a way the
  pages depend on**, otherwise a visitor can get a new page with an old script for up to ten minutes.
- **Prices update without anyone's computer.** `.github/workflows/update.yml` runs every hour while
  the US market is open (14:35 to 20:35 UTC) and once after the close, Monday to Friday.
- **Positions come from MarketWatch**, which needs a login, so a Claude scheduled task reads them in
  the browser on Mirko's computer and commits `data/holdings.json` and `data/transactions.json`.
- **No trade is placed automatically.** The site and the scheduled task only *propose* rebalancing
  trades. The portfolio manager approves each order and the reason is written in the trade log.

## For the team: how to update your section

You do not need to code. Open the file on GitHub, press the pencil, edit, press **Commit changes**.
The site refreshes within a few minutes.

| Who | What | File |
|---|---|---|
| Mirko | Message on the home page | `content/pm_note.md` |
| Mirko | Reason for each trade | `content/trade_rationale.json` |
| Mirko | Target weights | written by the allocation model; see below to set them by hand |
| Lorenzo | Indicators table | `content/risk/indicators.json` |
| Lorenzo | Risk note | `content/risk/notes.md` |
| Lorenzo | Allocation model and its settings | `models/igfinal/` (`config.py` holds every assumption) |
| Lorenzo | Other Python models | `models/` (see `models/README.md`) |
| Marek | One file per company | `content/fundamental/TICKER.md` |
| Andrea | Macro notes | `content/macro/YYYY-MM-DD-title.md` |
| Andrea | Event calendar | `content/macro/calendar.json` |
| Riccardo | Backtests | `content/backtest/name.md` + `name.csv` |
| Everyone | Philosophy and governance text | `content/philosophy.md` |
| Everyone | Team page | `content/team.json` |

To add a new note, copy an existing file in the same folder, rename it and change the text.
New files are picked up automatically.

### Company research (`content/fundamental/TICKER.md`)

```
---
ticker: MSFT
title: Microsoft
rating: Buy
target_price: 585
horizon: 3 months
catalysts: Q2 earnings in late January; Azure growth
author: Marek
updated: 2026-11-10
---
Your thesis in Markdown. **Bold**, lists and tables work.
```

Upside to target is calculated from the latest price, so only the target price needs maintaining.

### Macro notes (`content/macro/*.md`)

```
---
title: Regime check
date: 2026-11-10
regime: Late cycle, neutral
author: Andrea
---
Text in Markdown.
```

The `regime` of the most recent note is shown in the banner at the top of the macro section.

### Backtests (`content/backtest/name.md` and `name.csv`)

The header takes `title`, `author`, `updated`, `period` and `equity_csv`. **Every other line in the
header becomes a metric tile**, so write whatever you measured (`CAGR: 13.8%`, `Sharpe ratio: 0.81`).
The CSV has three columns, `date,strategy,benchmark`, both rebased to 100.

### Risk indicators (`content/risk/indicators.json`)

Each indicator has `name`, `value`, `signal` (`normal`, `caution` or `alert`) and `comment`.

### Trade rationale (`content/trade_rationale.json`)

One entry per trade, matched to the trade log by `date` (YYYY-MM-DD, New York date), `ticker` and
`side`. Trades without an entry show "Rationale not written yet".

## The allocation model

The plan of the fund is a model, not a list typed by hand. `models/igfinal/` is Lorenzo's toolkit,
with the few changes listed in `models/igfinal/CHANGES.md`: 70% of the fund in a replica of the S&P 500
(its 50 largest companies without NVIDIA, from Riccardo's replica study) and 30% in a sleeve of AI and
IPO-related names, sold on the day of the Anthropic IPO. Its benchmark is the one of the game:
max(0, S&P 500 return). The rules the portfolio manager set are in `config/rules.json` and are shown on
the Philosophy page; `research/` holds the studies behind them.

Before every site update the workflow runs `scripts/run_igfinal.py`, which:

1. writes the positions read from MarketWatch into `models/igfinal/input/holdings.csv`;
2. runs `models/igfinal/run_dashboard.py` on Yahoo closing prices;
3. copies the target weights into `content/targets.json`, so **Target weights and rebalancing** on
   the Portfolio page shows what to trade;
4. saves the results in `data/igfinal.json` (Risk page, under Team models) and the model's own
   dashboard in `data/igfinal/dashboard.html`.

The model prices the fund at the last completed session, so its numbers change once a day, with the
run of 22:30 UTC. If a trade is made after that close the model waits for the session to end
(positions and prices must belong to the same moment, or its permanent exit rule could fire on a
number that is not real). The exit, once made, is recorded in `models/igfinal/state/sleeve_exit.csv`;
the robot commits that folder and the model's logs.

To change the plan (sleeve names and size, IPO date, exit trigger, replica method, limits), edit
`models/igfinal/config.py`. To set target weights by hand instead, put `"source": "manual"` in
`content/targets.json`: the model then leaves that file alone. `config/rules.json` holds the limits
exported by the model on 13 November and is not rewritten.

## Private area

`private.html` is a login-protected page backed by a Supabase database (project `antifragile-portfolio`).

- Anyone can create an account with email and password, but an account sees nothing until it is
  unlocked **once** with a one-time access key. Keys are handed out by Mirko.
- The database stores only a fingerprint (SHA-256) of each key, never the key itself. The keys are
  kept in a local file outside this repository.
- Every table is protected row by row on the server: only unlocked members can read, and nobody can
  write from the website. Data and analyses are loaded by Claude on request.
- The Supabase address and publishable key in `config/fund.json` are public by design.

Tables: `analyses`, `trades`, `portfolio_snapshots`, `position_snapshots`, `watchlist`, `securities`
and `prices_daily` (daily adjusted closing prices of the S&P 500 companies since 1980).

The price history is loaded by the GitHub workflow **Load stock prices** (`scripts/load_prices.py`).
It needs the repository secret `SUPABASE_SECRET_KEY`. Run it once by hand with `since` set to
`1980-01-01`; after that it adds the new prices every Friday night. Only companies in the index
today are included, so long backtests on this data are flattered by survivorship bias.

European ETFs are added by the workflow **Load European ETFs** (`scripts/load_etfs.py`): every ETF
listed in EUR on Xetra whose fund size on Yahoo Finance is at least 1 billion, largest first, until
the row budget that keeps the database inside the free plan's 500 MB is reached.

## Settings

| File | What it holds |
|---|---|
| `config/fund.json` | Fund name, initial capital (10,000,000 USD), benchmark, start and end date, `demo_mode` |
| `config/rules.json` | Risk limits and buy/sell criteria. **The same numbers generate the alerts.** |
| `content/targets.json` | Target weights, written by the allocation model. |

Items still marked as placeholders: fund name and benchmark. The site measures the fund against SPY;
the benchmark of the game, max(0, S&P 500) from its start level, is the one the allocation model uses.

## Data files (generated, do not edit by hand)

`data/holdings.json` and `data/transactions.json` are written by the MarketWatch sync:

```json
{ "as_of": "2026-11-14T17:38:00+01:00", "net_worth": 10000000, "cash": 10000000,
  "positions": [ { "ticker": "AAPL", "name": "Apple Inc.", "shares": 100, "avg_cost": 250.10, "last_price": 268.00 } ] }
```

```json
{ "transactions": [ { "date": "2026-11-16T15:45:00+01:00", "ticker": "AAPL", "side": "buy", "shares": 100, "price": 250.10 } ] }
```

`side` is `buy`, `sell`, `short` or `cover`. A date without a time zone is read as New York time.

`data/igfinal.json` and `data/igfinal/` are written by the allocation model (previous section).

`scripts/update.py` then writes: `summary.json`, `positions.json`, `candles_1h.json`,
`candles_1d.json`, `exposures.json`, `risk.json`, `alerts.json`, `rebalance_suggestions.json`,
`models.json`, `projection.json`, `events.json`, `nav_history.json` (persistent
15-minute history), `meta_cache.json` (sector and country per ticker) and `content_index.json`.

`data/leaderboard.json` is also written by the MarketWatch sync. It stores our rank and the net
worth of every participant **as numbers only, without names**, because the site is public.

The sync is a Claude scheduled task that runs every evening after the US close on Mirko's
computer (it is skipped when the computer is off) and on request after a trade. It only reads the
Portfolio and Rankings pages of the game, never places an order, and hands what it read to
`scripts/marketwatch_sync.py`, which checks the reading and writes the three files. The script
refuses a ranking that contains anything but numbers and a transaction history shorter than the
one already saved.

## How the numbers are calculated

- **Fund value.** Positions over time are rebuilt by replaying the transaction log on the initial
  capital. On every 15-minute bar: `cash + sum(shares x price)`, once with open prices and once with
  close prices. Those values are resampled into hourly and daily candles. We never add up the highs
  and lows of single stocks, because they do not happen at the same moment.
- **Average cost and realised P&L** use the average-cost method.
- **Realised volatility and Sharpe** use daily returns and are shown after 10 trading days.
- **Risk at current weights** (VaR, expected shortfall, beta, correlations, share of risk) applies
  today's weights to one year of daily returns. VaR is given both as the historical 5th percentile
  and parametrically (1.645 x daily standard deviation).
- **Projection to the end of the game** redraws days at random from the past year of returns at
  today's weights (5,000 paths), with the average daily return set to zero. It shows the range of
  outcomes from risk alone and is not a forecast.
- **Stress test** multiplies each position's weight by its beta and the chosen market move. The
  historical episodes use each holding's actual price move, or beta times the market move when the
  holding has no price history for that period.
- **Earnings and ex-dividend dates** of the companies we hold or target are added to the Research
  calendar automatically.
- **Benchmark** is rebased to the initial capital at the first bar of the game.
- **If the price download fails**, the previous data is kept, the fund value falls back to the last
  MarketWatch reading and the site says prices are not up to date.
- **Consistency check.** If share counts rebuilt from the transaction log differ from MarketWatch,
  or the fund value differs by more than 0.5%, an alert appears on the home page.

Tickers are assumed to be quoted in USD on a US exchange. If Yahoo uses a different symbol from
MarketWatch, add `"ticker_map": {"BRK.B": "BRK-B"}` to `config/fund.json`.

## Running it on your own computer

```
pip install -r requirements.txt
python scripts/update.py            # real data
python scripts/make_demo.py         # rebuild the demo data
python -m http.server 8000          # then open http://localhost:8000
```

The site must be opened through a web server; double-clicking `index.html` does not load the data.

## Deployment

1. GitHub repo → Settings → Pages → Source: *Deploy from a branch*, branch `main`, folder `/ (root)`.
2. Custom domain `antifragileportfolio.eu` (already in the `CNAME` file). DNS records at register.it:

   | Type | Name | Value |
   |---|---|---|
   | A | @ | 185.199.108.153 |
   | A | @ | 185.199.109.153 |
   | A | @ | 185.199.110.153 |
   | A | @ | 185.199.111.153 |
   | CNAME | www | marianimirko.github.io |

3. When the DNS check in Settings → Pages turns green, tick **Enforce HTTPS**.
