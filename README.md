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
| Mirko | Target weights | `content/targets.json` |
| Lorenzo | Indicators table | `content/risk/indicators.json` |
| Lorenzo | Risk note | `content/risk/notes.md` |
| Lorenzo | Python models | `models/` (see `models/README.md`) |
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

## Settings

| File | What it holds |
|---|---|
| `config/fund.json` | Fund name, initial capital (10,000,000 USD), benchmark, start and end date, `demo_mode` |
| `config/rules.json` | Risk limits and buy/sell criteria. **The same numbers generate the alerts.** |
| `content/targets.json` | Target weights. Empty until the team agrees them. |

Items still marked as placeholders: fund name, benchmark (SPY) and every limit in `config/rules.json`.

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

`scripts/update.py` then writes: `summary.json`, `positions.json`, `candles_1h.json`,
`candles_1d.json`, `exposures.json`, `risk.json`, `alerts.json`, `rebalance_suggestions.json`,
`models.json`, `nav_history.json` (persistent 15-minute history), `meta_cache.json` (sector and
country per ticker) and `content_index.json`.

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
