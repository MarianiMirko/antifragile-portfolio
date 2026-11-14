#!/usr/bin/env python3
"""
make_demo.py - build an invented portfolio in data/demo/ so the site can be seen working.

Prices are simulated (seeded, so the result is always the same). Nothing here is real:
the site shows a "Demo data" banner while config/fund.json has "demo_mode": true.
The numbers go through exactly the same calculation as the live data (update.compute).
"""
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import update as U  # noqa: E402

ET = U.ET
DEMO_START = "2026-10-05"
DEMO_NOW = pd.Timestamp("2026-11-13 16:00", tz=ET).tz_convert("UTC")

#          last   vol   beta  drift  sector                    country          asset class     name
UNIVERSE = {
    "NVDA": (182, .45, 1.70, .24, "Technology", "United States", "Equity", "NVIDIA Corporation"),
    "MSFT": (512, .25, 1.10, .03, "Technology", "United States", "Equity", "Microsoft Corporation"),
    "AAPL": (268, .27, 1.15, .04, "Technology", "United States", "Equity", "Apple Inc."),
    "ASML": (985, .38, 1.50, .08, "Technology", "Netherlands", "Equity", "ASML Holding N.V."),
    "TSM":  (298, .36, 1.40, .15, "Technology", "Taiwan", "Equity", "Taiwan Semiconductor Manufacturing"),
    "JPM":  (305, .24, 1.05, .02, "Financial Services", "United States", "Equity", "JPMorgan Chase & Co."),
    "UNH":  (342, .30, 0.60, -.17, "Healthcare", "United States", "Equity", "UnitedHealth Group"),
    "NVO":  (58,  .35, 0.50, -.07, "Healthcare", "Denmark", "Equity", "Novo Nordisk A/S"),
    "XOM":  (117, .24, 0.70, .02, "Energy", "United States", "Equity", "Exxon Mobil Corporation"),
    "CAT":  (548, .28, 1.10, .05, "Industrials", "United States", "Equity", "Caterpillar Inc."),
    "PG":   (151, .16, 0.40, -.01, "Consumer Defensive", "United States", "Equity", "Procter & Gamble"),
    "LIN":  (452, .19, 0.80, .01, "Basic Materials", "United States", "Equity", "Linde plc"),
    "GLD":  (392, .15, 0.05, .05, "Funds & ETFs", "Global", "Gold ETF", "SPDR Gold Shares"),
    "DIS":  (104, .28, 1.10, -.08, "Communication Services", "United States", "Equity", "The Walt Disney Company"),
    "SPY":  (672, .14, 1.00, .025, "Funds & ETFs", "United States", "ETF", "SPDR S&P 500 ETF"),
}
TECH = {"NVDA", "MSFT", "AAPL", "ASML", "TSM"}
MARKET_VOL, TECH_VOL, BARS = 0.14, 0.15, 26


def simulate(seed=10):
    rng = np.random.default_rng(seed)
    days = pd.bdate_range("2025-11-10", "2026-11-13")
    n = len(days) * BARS
    stamps = pd.DatetimeIndex([d + pd.Timedelta(minutes=570 + 15 * k) for d in days for k in range(BARS)]
                              ).tz_localize(ET).tz_convert("UTC")
    first = np.arange(n) % BARS == 0
    # each day's variance: 30% overnight gap, 70% spread over the 26 bars
    scale = np.where(first, math.sqrt(0.30), 0.0)
    bar_sd = math.sqrt(0.70 / BARS)
    game = stamps >= U.to_utc(pd.Timestamp(DEMO_START))
    po, pc = {}, {}
    mkt_gap, mkt_bar = rng.standard_normal(n), rng.standard_normal(n)
    tec_gap, tec_bar = rng.standard_normal(n), rng.standard_normal(n)
    for t, (last, vol, beta, drift, *_rest) in UNIVERSE.items():
        d = 1 / math.sqrt(252)
        sys_var = (beta * MARKET_VOL) ** 2 + (TECH_VOL ** 2 if t in TECH else 0)
        idio = math.sqrt(max(vol ** 2 - sys_var, 0.02 ** 2)) if t != "SPY" else 0.0
        e_gap, e_bar = rng.standard_normal(n), rng.standard_normal(n)
        tech = TECH_VOL if t in TECH else 0.0
        gap = d * scale * (beta * MARKET_VOL * mkt_gap + tech * tec_gap + idio * e_gap)
        bar = d * bar_sd * (beta * MARKET_VOL * mkt_bar + tech * tec_bar + idio * e_bar)
        bar = bar + np.where(game, math.log1p(drift) / game.sum(), 0.08 / 252 / BARS)
        cum = np.cumsum(gap + bar)
        close = np.exp(cum)
        open_ = np.exp(cum - bar)
        k = last / close[-1]
        po[t], pc[t] = open_ * k, close * k
    po, pc = pd.DataFrame(po, index=stamps), pd.DataFrame(pc, index=stamps)
    daily = pc.copy()
    daily.index = daily.index.tz_convert(ET).tz_localize(None).normalize()
    daily = daily.groupby(level=0).last()
    return po, pc, daily


def main():
    cfg = U.load_json(U.ROOT / "config" / "fund.json")
    rules = U.load_json(U.ROOT / "config" / "rules.json")
    targets = U.load_json(U.ROOT / "scripts" / "demo_targets.json")
    targets["is_placeholder"] = True
    capital = cfg["initial_capital"]
    po, pc, daily = simulate()
    out = U.ROOT / "data" / "demo"

    def at(ts):
        return pc.index[pc.index.get_indexer([U.to_utc(pd.Timestamp(ts))], method="nearest")[0]]

    def trade(ts, ticker, side, weight=None, shares=None):
        stamp = at(ts)
        price = round(float(pc.loc[stamp, ticker]), 2)
        if shares is None:
            shares = int(round(weight * capital / price, -1))
        return {"date": (stamp + pd.Timedelta(minutes=14)).isoformat(), "ticker": ticker, "side": side,
                "shares": shares, "price": price}

    tg = targets["targets"]
    raw = []
    opening = ["NVDA", "MSFT", "AAPL", "ASML", "TSM", "JPM", "UNH", "NVO", "XOM", "CAT", "PG", "GLD"]
    for i, t in enumerate(opening):
        raw.append(trade(f"2026-10-05 {10 + i // 4}:{(i % 4) * 15:02d}", t, "buy", weight=tg[t]))
    raw.append(trade("2026-10-05 13:00", "DIS", "buy", weight=0.06))
    dis = raw[-1]["shares"]
    raw.append(trade("2026-10-21 10:15", "DIS", "sell", shares=dis))
    raw.append(trade("2026-10-21 10:45", "LIN", "buy", weight=tg["LIN"]))
    raw.append(trade("2026-11-04 15:00", "XOM", "buy", weight=0.01))
    U.write_json(out / "transactions.json", {"note": "Demo data", "transactions": raw})

    txs = U.normalise_transactions({"transactions": raw})
    meta = {t: {"name": v[7], "sector": v[4], "country": v[5], "asset_class": v[6]} for t, v in UNIVERSE.items()}
    U.write_json(out / "meta_cache.json", meta)
    for f in ("nav_history.json",):
        (out / f).unlink(missing_ok=True)
    res = U.compute(cfg, rules, targets, None, txs, po, pc, daily, meta, out, DEMO_NOW,
                    demo=True, start_date=DEMO_START)
    U.write_json(out / "holdings.json", {
        "note": "Demo data, same format the MarketWatch sync writes to data/holdings.json",
        "as_of": DEMO_NOW.isoformat(), "source": "demo", "net_worth": res["nav"], "cash": res["cash"],
        "buying_power": None, "cash_borrowed": 0, "short_reserve": 0, "rank": None,
        "positions": [{"ticker": p["ticker"], "name": p["name"], "shares": p["shares"],
                       "avg_cost": round(p["avg_cost"], 4), "last_price": round(p["price"], 2)} for p in res["positions"]]})
    U.build_content_index()
    print(f"demo fund value {res['nav']:,.2f}, cash {res['cash']:,.2f}, {len(res['positions'])} positions")


if __name__ == "__main__":
    main()
