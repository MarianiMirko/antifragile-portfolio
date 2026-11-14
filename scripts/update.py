#!/usr/bin/env python3
"""
update.py - recompute every data file the dashboard reads.

Reads   config/fund.json, config/rules.json, content/targets.json,
        data/holdings.json, data/transactions.json
Writes  data/summary.json, positions.json, candles_1h.json, candles_1d.json,
        exposures.json, risk.json, alerts.json, rebalance_suggestions.json,
        nav_history.json, meta_cache.json, content_index.json

Run     python scripts/update.py            (downloads prices with yfinance)
        python scripts/update.py --offline  (no download; uses MarketWatch prices)

How the fund value is built
---------------------------
Positions over time come from replaying data/transactions.json on top of the
initial capital. On every 15-minute bar the fund value is
    cash + sum(shares x price)
computed once with the bar's open prices and once with its close prices.
Those 15-minute values are then resampled into hourly and daily candles.
(We never add up the highs and lows of single stocks: they do not happen at
the same moment, so that would overstate the range.)
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
ET = "America/New_York"
Z95 = 1.6448536269514722          # 95% one-sided normal quantile
ES95_K = 2.0627128075074257       # normal pdf(Z95) / 0.05
SIGN = {"buy": 1, "cover": 1, "sell": -1, "short": -1}
MIN_DAYS_REALISED = 10            # trading days needed before realised vol / Sharpe are shown
REGIONS = {
    "United States": "North America", "Canada": "North America",
    "Netherlands": "Europe", "Denmark": "Europe", "Germany": "Europe", "France": "Europe",
    "United Kingdom": "Europe", "Switzerland": "Europe", "Ireland": "Europe", "Italy": "Europe",
    "Spain": "Europe", "Sweden": "Europe", "Norway": "Europe", "Finland": "Europe", "Belgium": "Europe",
    "Taiwan": "Asia Pacific", "Japan": "Asia Pacific", "China": "Asia Pacific", "South Korea": "Asia Pacific",
    "Hong Kong": "Asia Pacific", "India": "Asia Pacific", "Australia": "Asia Pacific", "Singapore": "Asia Pacific",
    "Brazil": "Latin America", "Mexico": "Latin America", "Argentina": "Latin America",
}


# ----------------------------------------------------------------------------
# small helpers
# ----------------------------------------------------------------------------
def load_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def _clean(o):
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (float, np.floating)):
        f = float(o)
        if math.isnan(f) or math.isinf(f):
            return None
        return round(f, 6)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, (pd.Timestamp, datetime)):
        return o.isoformat()
    return o


def write_json(path, obj, compact=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(_clean(obj), indent=None if compact else 1, allow_nan=False,
                      separators=(",", ":") if compact else None, ensure_ascii=False)
    path.write_text(text + "\n", encoding="utf-8")


def to_utc(value):
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:               # a time without a zone is read as New York time
        ts = ts.tz_localize(ET)
    return ts.tz_convert("UTC")


def pct(x, digits=1):
    return f"{x * 100:.{digits}f}%"


def normalise_transactions(raw):
    out = []
    for t in (raw or {}).get("transactions", []):
        side = str(t["side"]).lower()
        if side not in SIGN:
            raise ValueError(f"Unknown side '{t['side']}' in transactions.json")
        out.append({
            "ts": to_utc(t["date"]), "ticker": str(t["ticker"]).upper(), "side": side,
            "shares": float(t["shares"]), "price": float(t["price"]), "fee": float(t.get("fee", 0) or 0),
        })
    return sorted(out, key=lambda t: t["ts"])


def replay_book(txs, capital):
    """Average-cost book: final shares, average cost, realised P&L and cash."""
    book, cash = {}, float(capital)
    for t in txs:
        b = book.setdefault(t["ticker"], {"shares": 0.0, "avg_cost": 0.0, "realized": 0.0})
        d, p, q = SIGN[t["side"]] * t["shares"], t["price"], b["shares"]
        if q == 0 or (q > 0) == (d > 0):                      # opening or adding
            b["avg_cost"] = (abs(q) * b["avg_cost"] + abs(d) * p) / (abs(q) + abs(d))
        else:                                                 # reducing or closing
            closed = min(abs(d), abs(q))
            b["realized"] += closed * (p - b["avg_cost"]) * (1 if q > 0 else -1)
            if abs(d) > abs(q):                               # flipped through zero
                b["avg_cost"] = p
        b["shares"] = q + d
        if abs(b["shares"]) < 1e-9:
            b["shares"], b["avg_cost"] = 0.0, 0.0
        cash -= d * p + t["fee"]
    return book, cash


def position_series(txs, grid, tickers, capital):
    shares = pd.DataFrame(0.0, index=grid, columns=tickers)
    cash = pd.Series(float(capital), index=grid)
    for t in txs:
        mask = grid >= t["ts"]
        d = SIGN[t["side"]] * t["shares"]
        shares.loc[mask, t["ticker"]] += d
        cash[mask] -= d * t["price"] + t["fee"]
    return shares, cash


def session_grid(start_utc, end_utc):
    """15-minute bars of the regular US session on weekdays (used when offline)."""
    days = pd.bdate_range(start_utc.tz_convert(ET).normalize().tz_localize(None),
                          end_utc.tz_convert(ET).normalize().tz_localize(None))
    stamps = []
    for d in days:
        stamps.extend(pd.date_range(d + pd.Timedelta(hours=9, minutes=30), periods=26, freq="15min"))
    idx = pd.DatetimeIndex(stamps).tz_localize(ET).tz_convert("UTC")
    return idx[(idx >= start_utc) & (idx <= end_utc)]


# ----------------------------------------------------------------------------
# market data
# ----------------------------------------------------------------------------
def yahoo_symbol(ticker, cfg):
    return (cfg.get("ticker_map") or {}).get(ticker, ticker.replace(".", "-"))


def fetch_yfinance(tickers, cfg):
    """Returns (open_15m, close_15m, daily_close) as DataFrames with our tickers as columns."""
    import yfinance as yf

    symbols = {t: yahoo_symbol(t, cfg) for t in tickers}
    names = list(dict.fromkeys(symbols.values()))

    def grab(**kw):
        df = yf.download(names, progress=False, threads=True, group_by="column", **kw)
        if df is None or df.empty:
            raise RuntimeError("yfinance returned no data")
        if not isinstance(df.columns, pd.MultiIndex):
            df.columns = pd.MultiIndex.from_product([df.columns, names])
        return df

    intr = grab(period="60d", interval="15m", auto_adjust=False, prepost=False)
    day = grab(period="1y", interval="1d", auto_adjust=True)

    def pick(df, field):
        part = df[field].copy()
        part = part.rename(columns={v: k for k, v in symbols.items()})
        return part.reindex(columns=tickers)

    po, pc = pick(intr, "Open"), pick(intr, "Close")
    for f in (po, pc):
        f.index = (f.index.tz_localize(ET) if f.index.tz is None else f.index).tz_convert("UTC")
    daily = pick(day, "Close")
    daily.index = pd.DatetimeIndex(daily.index).tz_localize(None).normalize()
    bench = cfg["benchmark"]["ticker"]
    if pc[bench].dropna().empty:
        raise RuntimeError("no benchmark prices")
    missing = [t for t in tickers if pc[t].dropna().empty]
    if missing:
        raise RuntimeError("no prices for " + ", ".join(missing))
    return po, pc, daily


def fetch_meta(tickers, cache, cfg, holdings, online=True):
    """Name, sector, country and asset class per ticker, cached in data/meta_cache.json."""
    mw_names = {p["ticker"].upper(): p.get("name") for p in (holdings or {}).get("positions", [])}
    for t in tickers:
        if t in cache and cache[t].get("sector"):
            continue
        entry = {"name": mw_names.get(t) or t, "sector": "Unclassified", "country": "Unknown", "asset_class": "Equity"}
        if online:
            try:
                import yfinance as yf
                info = yf.Ticker(yahoo_symbol(t, cfg)).info or {}
                qt = (info.get("quoteType") or "EQUITY").upper()
                entry["name"] = info.get("longName") or info.get("shortName") or entry["name"]
                if qt == "ETF":
                    entry.update(sector="Funds & ETFs", country=info.get("country") or "Global", asset_class="ETF")
                else:
                    entry.update(sector=info.get("sector") or "Unclassified", country=info.get("country") or "Unknown")
            except Exception as exc:  # keep going with the placeholder entry
                print(f"meta lookup failed for {t}: {exc}", file=sys.stderr)
                cache.setdefault(t, entry)
                continue
        cache[t] = entry
    return cache


# ----------------------------------------------------------------------------
# candles
# ----------------------------------------------------------------------------
def build_candles(bars):
    """bars: DataFrame indexed by UTC bar start with columns o, c, b (benchmark, may be NaN)."""
    loc = bars.copy()
    loc.index = loc.index.tz_convert(ET)
    loc["hi"] = loc[["o", "c"]].max(axis=1)
    loc["lo"] = loc[["o", "c"]].min(axis=1)
    day = loc.index.normalize()
    mins = loc.index.hour * 60 + loc.index.minute - 570
    bucket = np.clip(mins // 60, 0, None)

    def agg(keys):
        g = loc.groupby(keys)
        return g.agg(open=("o", "first"), high=("hi", "max"), low=("lo", "min"), close=("c", "last"), b=("b", "last"))

    h = agg([day, bucket])
    hourly, hourly_b = [], []
    for (d, k), r in h.iterrows():
        ts = int((d + pd.Timedelta(minutes=570 + 60 * int(k))).tz_convert("UTC").timestamp())
        hourly.append({"time": ts, "open": r.open, "high": r.high, "low": r.low, "close": r.close})
        if not pd.isna(r.b):
            hourly_b.append({"time": ts, "value": r.b})
    dly = agg(day)
    daily, daily_b = [], []
    for d, r in dly.iterrows():
        ds = d.strftime("%Y-%m-%d")
        daily.append({"time": ds, "open": r.open, "high": r.high, "low": r.low, "close": r.close})
        if not pd.isna(r.b):
            daily_b.append({"time": ds, "value": r.b})
    return hourly, hourly_b, daily, daily_b


# ----------------------------------------------------------------------------
# the main calculation
# ----------------------------------------------------------------------------
def compute(cfg, rules, targets, holdings, txs, po, pc, daily, meta, out_dir, now,
            status="ok", price_source="yfinance", demo=False, start_date=None):
    out_dir = Path(out_dir)
    capital = float(cfg["initial_capital"])
    bench = cfg["benchmark"]["ticker"]
    lim = rules["limits"]
    start = to_utc(pd.Timestamp(start_date or cfg["start_date"]))
    end_date = pd.Timestamp(cfg["end_date"])

    book, cash_now = replay_book(txs, capital)
    held = [t for t, b in book.items() if b["shares"] != 0]
    traded = list(book.keys())

    # ---- fund value on the 15-minute grid --------------------------------
    grid = pc.index[(pc.index >= start) & (pc.index <= now)]
    po, pc = po.reindex(grid).ffill().bfill(), pc.reindex(grid).ffill().bfill()
    shares, cash = position_series(txs, grid, traded, capital)
    nav_o = cash + (shares * po[traded]).sum(axis=1) if traded else cash.copy()
    nav_c = cash + (shares * pc[traded]).sum(axis=1) if traded else cash.copy()
    has_bench = bench in pc.columns and not pc[bench].dropna().empty
    bench_rebased = (pc[bench] / po[bench].iloc[0] * capital) if has_bench else pd.Series(np.nan, index=grid)

    # ---- persistent history: old bars survive when the data source drops them
    hist_path = out_dir / "nav_history.json"
    hist = {int(r[0]): r[1:] for r in (load_json(hist_path, {}) or {}).get("bars", [])}
    for ts, o, c, b in zip(grid, nav_o, nav_c, bench_rebased):
        hist[int(ts.timestamp())] = [round(float(o), 2), round(float(c), 2), None if pd.isna(b) else round(float(b), 2)]
    rows = sorted(hist.items())
    write_json(hist_path, {"note": "15-minute fund value: [unix time, open, close, benchmark rebased]. Generated file.",
                           "bars": [[k] + v for k, v in rows]}, compact=True)
    bars = pd.DataFrame([v for _, v in rows], columns=["o", "c", "b"],
                        index=pd.to_datetime([k for k, _ in rows], unit="s", utc=True)).astype(float)

    hourly, hourly_b, dcandles, daily_b = build_candles(bars)
    write_json(out_dir / "candles_1h.json", {"candles": hourly, "benchmark": hourly_b}, compact=True)
    write_json(out_dir / "candles_1d.json", {"candles": dcandles, "benchmark": daily_b}, compact=True)

    # ---- headline numbers -------------------------------------------------
    nav = float(bars["c"].iloc[-1])
    as_of = min(bars.index[-1] + pd.Timedelta(minutes=15), now)
    closes = pd.Series([c["close"] for c in dcandles], index=pd.to_datetime([c["time"] for c in dcandles]))
    prev_nav = float(closes.iloc[-2]) if len(closes) > 1 else capital
    rets = pd.concat([pd.Series([capital]), closes]).pct_change().iloc[1:]
    rets.index = closes.index
    n_days = len(rets)
    bcl = pd.Series([c["value"] for c in daily_b], index=pd.to_datetime([c["time"] for c in daily_b]))
    brets = pd.concat([pd.Series([capital]), bcl]).pct_change().iloc[1:] if len(bcl) else pd.Series(dtype=float)
    if len(bcl):
        brets.index = bcl.index
    bench_return = float(bcl.iloc[-1] / capital - 1) if len(bcl) else None
    total_return = nav / capital - 1

    peak = bars["c"].cummax().clip(lower=capital)
    dd_series = bars["c"] / peak - 1
    max_dd = float(dd_series.min())
    hclose = pd.Series([c["close"] for c in hourly], index=[c["time"] for c in hourly])
    hdd = hclose / hclose.cummax().clip(lower=capital) - 1

    realised_vol = float(rets.std(ddof=1) * math.sqrt(252)) if n_days >= MIN_DAYS_REALISED else None
    vol_20d = float(rets.iloc[-20:].std(ddof=1) * math.sqrt(252)) if n_days >= 20 else None
    rf_d = float(cfg.get("risk_free_rate", 0)) / 252
    sharpe = float((rets.mean() - rf_d) * 252 / realised_vol) if realised_vol else None
    rolling = (rets.rolling(20).std(ddof=1) * math.sqrt(252)).dropna()
    realised_beta = None
    if n_days >= MIN_DAYS_REALISED and len(brets) == n_days and brets.var() > 0:
        realised_beta = float(np.cov(rets, brets)[0, 1] / brets.var(ddof=1))

    # ---- positions --------------------------------------------------------
    last_day = grid[-1].tz_convert(ET).normalize() if len(grid) else None
    today_mask = grid.tz_convert(ET).normalize() == last_day if len(grid) else np.array([], dtype=bool)
    prev_idx = grid[~today_mask][-1] if len(grid) and (~today_mask).any() else None
    tgt = {k.upper(): float(v) for k, v in (targets or {}).get("targets", {}).items()}
    positions = []
    for t in held:
        b, m = book[t], meta.get(t, {})
        price = float(pc[t].iloc[-1])
        value = b["shares"] * price
        prev_close = float(pc.loc[prev_idx, t]) if prev_idx is not None else b["avg_cost"]
        shares_prev = float(shares.loc[prev_idx, t]) if prev_idx is not None else 0.0
        net_today = sum(SIGN[x["side"]] * x["shares"] * x["price"] for x in txs
                        if x["ticker"] == t and (prev_idx is None or x["ts"] > prev_idx))
        unreal = b["shares"] * (price - b["avg_cost"])
        positions.append({
            "ticker": t, "name": m.get("name", t), "sector": m.get("sector", "Unclassified"),
            "country": m.get("country", "Unknown"), "asset_class": m.get("asset_class", "Equity"),
            "shares": b["shares"], "avg_cost": b["avg_cost"], "price": price, "prev_close": prev_close,
            "value": value, "weight": value / nav, "cost_basis": b["shares"] * b["avg_cost"],
            "unrealized": unreal, "unrealized_pct": (price / b["avg_cost"] - 1) * (1 if b["shares"] > 0 else -1),
            "day_pnl": value - shares_prev * prev_close - net_today, "day_pct": price / prev_close - 1,
            "realized": b["realized"], "contribution": (unreal + b["realized"]) / capital,
            "target_weight": tgt.get(t), "drift": (value / nav - tgt[t]) if t in tgt else None,
        })
    positions.sort(key=lambda p: -p["value"])
    invested = sum(p["value"] for p in positions)
    cash_now = nav - invested
    cash_w = cash_now / nav
    closed = [{"ticker": t, "name": meta.get(t, {}).get("name", t), "realized": b["realized"],
               "contribution": b["realized"] / capital} for t, b in book.items() if b["shares"] == 0 and b["realized"] != 0]
    realized_total = sum(b["realized"] for b in book.values())
    unreal_total = sum(p["unrealized"] for p in positions)
    write_json(out_dir / "positions.json", {
        "as_of": as_of, "nav": nav, "cash": cash_now, "cash_weight": cash_w, "invested": invested,
        "unrealized_total": unreal_total, "realized_total": realized_total,
        "positions": positions, "closed": closed,
        "transactions": [{"date": t["ts"], "ticker": t["ticker"], "side": t["side"], "shares": t["shares"],
                          "price": t["price"], "amount": t["shares"] * t["price"]} for t in reversed(txs)],
    })

    # ---- exposures --------------------------------------------------------
    def bucket(key, cash_label="Cash"):
        agg = {}
        for p in positions:
            k = key(p)
            agg[k] = agg.get(k, 0.0) + p["weight"]
        rows_ = sorted(({"name": k, "weight": v} for k, v in agg.items()), key=lambda r: -r["weight"])
        return rows_ + [{"name": cash_label, "weight": cash_w, "is_cash": True}]

    exposures = {
        "sector": bucket(lambda p: p["sector"]),
        "country": bucket(lambda p: p["country"]),
        "region": bucket(lambda p: REGIONS.get(p["country"], "Other")),
        "asset_class": bucket(lambda p: p["asset_class"]),
    }
    write_json(out_dir / "exposures.json", exposures)

    # ---- risk at current weights (one year of daily history) ---------------
    ex = {"available": False}
    pos_risk, corr = [], None
    if daily is not None and held:
        R = daily[held].pct_change().dropna(how="any")
        if len(R) >= 30:
            w = np.array([book[t]["shares"] * float(pc[t].iloc[-1]) / nav for t in held])
            sim = R.values @ w
            cov = R.cov().values
            var_p = float(w @ cov @ w)
            sd = math.sqrt(var_p)
            q = float(np.quantile(sim, 0.05))
            ex = {"available": True, "lookback_days": len(R), "vol": sd * math.sqrt(252),
                  "var_95_hist": -q, "es_95_hist": -float(sim[sim <= q].mean()),
                  "var_95_param": Z95 * sd, "es_95_param": ES95_K * sd, "beta": None}
            bser = daily[bench].pct_change().reindex(R.index) if bench in daily.columns else None
            if bser is not None and bser.notna().sum() > 30:
                ex["beta"] = float(np.cov(sim, bser.fillna(0).values)[0, 1] / bser.var(ddof=1))
            mrc = cov @ w
            for i, t in enumerate(held):
                beta_i = None
                if bser is not None and bser.notna().sum() > 30:
                    beta_i = float(np.cov(R[t].values, bser.fillna(0).values)[0, 1] / bser.var(ddof=1))
                pos_risk.append({"ticker": t, "weight": float(w[i]), "vol": float(R[t].std(ddof=1) * math.sqrt(252)),
                                 "beta": beta_i, "risk_contribution": float(w[i] * mrc[i] / var_p) if var_p > 0 else 0.0})
            pos_risk.sort(key=lambda r: -r["risk_contribution"])
            order = [r["ticker"] for r in sorted(pos_risk, key=lambda r: -r["weight"])]
            corr = {"tickers": order, "matrix": R[order].corr().round(3).values.tolist()}
    risk = {
        "as_of": as_of, "nav": nav,
        "realised": {"n_days": n_days, "min_days": MIN_DAYS_REALISED, "vol": realised_vol, "vol_20d": vol_20d,
                     "beta": realised_beta, "max_drawdown": max_dd, "sharpe": sharpe,
                     "rolling_vol_20d": [[d.strftime("%Y-%m-%d"), v] for d, v in rolling.items()],
                     "drawdown": [[int(k), v] for k, v in hdd.items()]},
        "ex_ante": ex, "positions": pos_risk, "correlation": corr,
    }
    write_json(out_dir / "risk.json", risk)

    # ---- targets and rebalancing proposals ---------------------------------
    thr = float(lim.get("drift_threshold", 0.02))
    table, suggestions = [], []
    by_ticker = {p["ticker"]: p for p in positions}
    for t in sorted(set(tgt) | set(by_ticker), key=lambda k: (k == "CASH", -tgt.get(k, 0), k)):
        if t == "CASH":
            table.append({"ticker": "CASH", "name": "Cash", "weight": cash_w, "target_weight": tgt.get("CASH"),
                          "drift": cash_w - tgt["CASH"] if "CASH" in tgt else None, "action": None, "shares": 0,
                          "flag": False})
            continue
        p = by_ticker.get(t)
        w_now, w_tgt = (p["weight"] if p else 0.0), tgt.get(t, 0.0)
        price = p["price"] if p else (float(pc[t].iloc[-1]) if t in pc.columns and not pd.isna(pc[t].iloc[-1]) else None)
        drift = w_now - w_tgt
        n = int((w_tgt - w_now) * nav / price) if price else 0
        if t not in tgt and p:                      # held but not in the target list: no proposal, just show it
            n = 0
        blocked = None
        if p and n > 0 and p["unrealized_pct"] <= lim["stop_loss_pct"]:
            n = 0                                   # never propose adding to a position that hit its stop-loss
            blocked = "Stop-loss hit: no top-up"
        flag = abs(drift) > thr and t in tgt and n != 0
        row = {"ticker": t, "name": meta.get(t, {}).get("name", t), "weight": w_now, "target_weight": tgt.get(t),
               "drift": drift if t in tgt else None, "price": price,
               "action": ("buy" if n > 0 else "sell") if n else None, "shares": abs(n),
               "est_value": abs(n) * price if price else None, "flag": flag, "blocked": blocked}
        table.append(row)
        if flag:
            suggestions.append({**row, "reason": f"{t} is {pct(abs(drift))} {'above' if drift > 0 else 'below'} its "
                                f"{pct(w_tgt)} target (threshold {pct(thr)})."})
    suggestions.sort(key=lambda s: -abs(s["drift"]))
    write_json(out_dir / "rebalance_suggestions.json", {
        "generated_at": now, "nav": nav, "drift_threshold": thr,
        "note": "Proposals only. No order is placed until the portfolio manager approves it.",
        "targets_are_placeholder": bool((targets or {}).get("is_placeholder")),
        "table": table, "suggestions": suggestions})

    # ---- rules: are we inside our own limits? ------------------------------
    alerts, status_rows = [], []

    def rule(rid, name, limit, current, ok, sev="breach"):
        status_rows.append({"id": rid, "rule": name, "limit": limit, "current": current,
                            "status": "ok" if ok else sev})

    def alert(sev, title, message, ticker=None):
        alerts.append({"severity": sev, "title": title, "message": message, "ticker": ticker})

    top = positions[0] if positions else None
    over = [p for p in positions if p["weight"] > lim["max_position_weight"]]
    rule("position", "Largest single position", f"at most {pct(lim['max_position_weight'], 0)}",
         f"{pct(top['weight'])} ({top['ticker']})" if top else "no positions", not over)
    for p in over:
        alert("breach", f"{p['ticker']} above the position limit",
              f"{p['ticker']} is {pct(p['weight'])} of the fund; the limit is {pct(lim['max_position_weight'], 0)}.", p["ticker"])

    sectors = [s for s in exposures["sector"] if not s.get("is_cash")]
    over_s = [s for s in sectors if s["weight"] > lim["max_sector_weight"]]
    rule("sector", "Largest sector", f"at most {pct(lim['max_sector_weight'], 0)}",
         f"{pct(sectors[0]['weight'])} ({sectors[0]['name']})" if sectors else "no positions", not over_s)
    for s in over_s:
        alert("breach", f"{s['name']} above the sector limit",
              f"{s['name']} is {pct(s['weight'])} of the fund; the limit is {pct(lim['max_sector_weight'], 0)}.")

    cash_ok = lim["min_cash_weight"] <= cash_w <= lim["max_cash_weight"]
    rule("cash", "Cash", f"{pct(lim['min_cash_weight'], 0)} to {pct(lim['max_cash_weight'], 0)}", pct(cash_w), cash_ok,
         "breach" if cash_w < lim["min_cash_weight"] else "warning")
    if cash_w < lim["min_cash_weight"]:
        alert("breach", "Cash below the minimum", f"Cash is {pct(cash_w)}; the minimum is {pct(lim['min_cash_weight'], 0)}.")
    elif cash_w > lim["max_cash_weight"]:
        alert("warning", "Cash above the maximum", f"Cash is {pct(cash_w)}; the maximum is {pct(lim['max_cash_weight'], 0)}.")

    n_pos = len(positions)
    n_ok = lim["min_positions"] <= n_pos <= lim["max_positions"]
    rule("count", "Number of positions", f"{lim['min_positions']} to {lim['max_positions']}", str(n_pos), n_ok, "warning")
    if not n_ok:
        alert("warning", "Number of positions outside the range",
              f"The fund holds {n_pos} positions; the range is {lim['min_positions']} to {lim['max_positions']}.")

    stopped = [p for p in positions if p["unrealized_pct"] <= lim["stop_loss_pct"]]
    worst = min(positions, key=lambda p: p["unrealized_pct"]) if positions else None
    rule("stop", "Stop-loss", f"sell at {pct(lim['stop_loss_pct'], 0)} from average cost",
         f"worst is {pct(worst['unrealized_pct'])} ({worst['ticker']})" if worst else "no positions", not stopped)
    for p in stopped:
        alert("breach", f"{p['ticker']} hit its stop-loss",
              f"{p['ticker']} is {pct(p['unrealized_pct'])} from its average cost; the stop-loss is {pct(lim['stop_loss_pct'], 0)}.", p["ticker"])

    if ex.get("available"):
        var_ok = ex["var_95_hist"] <= lim["max_var_95_1d"]
        rule("var", "One-day 95% VaR", f"at most {pct(lim['max_var_95_1d'])}", pct(ex["var_95_hist"], 2), var_ok)
        if not var_ok:
            alert("breach", "VaR above its limit",
                  f"One-day 95% VaR is {pct(ex['var_95_hist'], 2)} of the fund; the limit is {pct(lim['max_var_95_1d'])}.")
    else:
        rule("var", "One-day 95% VaR", f"at most {pct(lim['max_var_95_1d'])}", "not available yet", True)

    margin_used = cash_now < -1
    rule("margin", "Borrowing (margin)", "allowed" if lim["allow_margin"] else "not allowed",
         "in use" if margin_used else "none", lim["allow_margin"] or not margin_used)
    if margin_used and not lim["allow_margin"]:
        alert("breach", "Margin in use", f"The fund has borrowed ${-cash_now:,.0f}; our rules do not allow borrowing.")
    shorts = [p["ticker"] for p in positions if p["shares"] < 0]
    rule("short", "Short positions", "allowed" if lim["allow_short"] else "not allowed",
         ", ".join(shorts) if shorts else "none", lim["allow_short"] or not shorts)
    if shorts and not lim["allow_short"]:
        alert("breach", "Short positions open", f"Short in {', '.join(shorts)}; our rules do not allow short selling.")

    drifts = [r for r in table if r.get("drift") is not None and r["ticker"] != "CASH"]
    maxd = max(drifts, key=lambda r: abs(r["drift"])) if drifts else None
    rule("drift", "Drift from target weight", f"rebalance beyond {pct(thr, 0)}",
         f"largest is {maxd['drift'] * 100:+.1f} pts ({maxd['ticker']})" if maxd else "no targets set",
         not suggestions, "warning")
    for s in suggestions:
        alert("warning", f"Rebalance {s['ticker']}: {s['action']} {s['shares']:,} shares",
              s["reason"] + f" Proposed: {s['action']} {s['shares']:,} shares (about ${s['est_value']:,.0f}).", s["ticker"])

    # ---- does our calculation agree with MarketWatch? ----------------------
    mw = None
    if holdings:
        mw_nw = holdings.get("net_worth")
        mw = {"net_worth": mw_nw, "as_of": holdings.get("as_of"), "rank": holdings.get("rank"),
              "diff": (nav - mw_nw) if mw_nw else None, "diff_pct": (nav / mw_nw - 1) if mw_nw else None}
        mw_shares = {p["ticker"].upper(): float(p["shares"]) for p in holdings.get("positions", [])}
        ours = {t: book[t]["shares"] for t in held}
        mism = sorted(t for t in set(mw_shares) | set(ours) if abs(mw_shares.get(t, 0) - ours.get(t, 0)) > 1e-6)
        if mism and not demo:
            alert("breach", "Positions differ from MarketWatch",
                  "Share counts rebuilt from the transaction log do not match MarketWatch for: " + ", ".join(mism) +
                  ". Check data/transactions.json.")
        if mw_nw and abs(nav / mw_nw - 1) > 0.005 and not demo:
            alert("warning", "Fund value differs from MarketWatch",
                  f"We compute ${nav:,.0f}; MarketWatch showed ${mw_nw:,.0f} at its last sync.")
    if status != "ok":
        alert("warning", "Prices are not up to date",
              "The price download failed, so the site shows the last prices read from MarketWatch.")

    order = {"breach": 0, "warning": 1, "info": 2}
    alerts.sort(key=lambda a: order[a["severity"]])
    write_json(out_dir / "alerts.json", {
        "generated_at": now, "alerts": alerts, "rules": status_rows,
        "rules_are_placeholder": bool(rules.get("is_placeholder")),
        "rules_ok": sum(r["status"] == "ok" for r in status_rows), "rules_total": len(status_rows)})

    # ---- summary ------------------------------------------------------------
    vol_value, vol_basis = (realised_vol, "realised") if realised_vol else (ex.get("vol"), "at current weights")
    write_json(out_dir / "summary.json", {
        "generated_at": now, "as_of": as_of, "status": status, "price_source": price_source, "demo": demo,
        "initial_capital": capital, "nav": nav, "cash": cash_now, "cash_weight": cash_w, "invested": invested,
        "n_positions": n_pos, "day_change": nav - prev_nav, "day_change_pct": nav / prev_nav - 1,
        "total_change": nav - capital, "total_return": total_return,
        "benchmark": {"ticker": bench, "name": cfg["benchmark"].get("name", bench), "return": bench_return},
        "excess_return": (total_return - bench_return) if bench_return is not None else None,
        "volatility": vol_value, "volatility_basis": vol_basis if vol_value else None,
        "sharpe": sharpe, "max_drawdown": max_dd, "trading_days": n_days,
        "realized_pnl": realized_total, "unrealized_pnl": unreal_total,
        "start_date": (start_date or cfg["start_date"]), "end_date": cfg["end_date"],
        "days_left": max(0, (end_date - pd.Timestamp(now.tz_convert(ET).date())).days),
        "marketwatch": mw, "rules_ok": sum(r["status"] == "ok" for r in status_rows),
        "rules_total": len(status_rows), "n_alerts": len(alerts),
    })
    ctx = {"nav": nav, "cash": cash_now, "invested": invested, "positions": positions,
           "weights": {p["ticker"]: p["weight"] for p in positions}, "daily": daily,
           "benchmark": bench, "config": cfg, "rules": rules, "as_of": as_of}
    run_models(ctx, out_dir, now)
    return ctx


# ----------------------------------------------------------------------------
# when the price download fails and good data already exists
# ----------------------------------------------------------------------------
def stale_update(holdings, out_dir, now):
    """Leave candles, risk and history untouched; refresh value from MarketWatch and flag it."""
    out_dir = Path(out_dir)
    summary = load_json(out_dir / "summary.json")
    summary["status"] = "stale"
    summary["price_source"] = "marketwatch"
    summary["stale_since"] = summary.get("stale_since") or now.isoformat()
    if holdings and holdings.get("net_worth"):
        summary["nav"] = holdings["net_worth"]
        summary["total_change"] = holdings["net_worth"] - summary["initial_capital"]
        summary["total_return"] = holdings["net_worth"] / summary["initial_capital"] - 1
        summary["as_of"] = holdings.get("as_of", summary["as_of"])
    write_json(out_dir / "summary.json", summary)
    al = load_json(out_dir / "alerts.json", {"alerts": [], "rules": []})
    if not any(a["title"] == "Prices are not up to date" for a in al["alerts"]):
        al["alerts"].append({"severity": "warning", "title": "Prices are not up to date", "ticker": None,
                             "message": "The price download failed, so the site shows the last prices read from MarketWatch."})
        write_json(out_dir / "alerts.json", al)


# ----------------------------------------------------------------------------
# content index: lets the static site find the team's files
# ----------------------------------------------------------------------------
def build_content_index():
    idx = {}
    for section in ("fundamental", "macro", "backtest"):
        folder = ROOT / "content" / section
        idx[section] = sorted(p.name for p in folder.glob("*.md")) if folder.exists() else []
    write_json(ROOT / "data" / "content_index.json", idx)


# ----------------------------------------------------------------------------
# team models: every .py file in models/ with a run(ctx) function is executed
# ----------------------------------------------------------------------------
def run_models(ctx, out_dir, now):
    import importlib.util
    import traceback

    results = []
    folder = ROOT / "models"
    for path in sorted(folder.glob("*.py")) if folder.exists() else []:
        if path.name.startswith("_"):
            continue
        entry = {"id": path.stem, "title": path.stem, "error": None}
        try:
            spec = importlib.util.spec_from_file_location(f"fund_model_{path.stem}", path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            entry.update(mod.run(ctx) or {})
        except Exception as exc:                 # one broken model must not stop the update
            entry["error"] = f"{type(exc).__name__}: {exc}"
            print(f"model {path.name} failed:\n{traceback.format_exc()}", file=sys.stderr)
        results.append(entry)
    write_json(Path(out_dir) / "models.json", {"generated_at": now, "models": results})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true", help="do not download prices")
    args = ap.parse_args()

    cfg = load_json(ROOT / "config" / "fund.json")
    rules = load_json(ROOT / "config" / "rules.json")
    targets = load_json(ROOT / "content" / "targets.json", {"targets": {}})
    holdings = load_json(ROOT / "data" / "holdings.json", {"positions": []})
    txs = normalise_transactions(load_json(ROOT / "data" / "transactions.json", {"transactions": []}))
    out = ROOT / "data"
    now = pd.Timestamp(datetime.now(timezone.utc))
    bench = cfg["benchmark"]["ticker"]

    build_content_index()

    book, _ = replay_book(txs, cfg["initial_capital"])
    tickers = list(dict.fromkeys(
        [t for t in book] + [p["ticker"].upper() for p in holdings.get("positions", [])] +
        [t.upper() for t in targets.get("targets", {}) if t.upper() != "CASH"] + [bench]))

    po = pc = daily = None
    status, source = "ok", "yfinance"
    if not args.offline:
        try:
            po, pc, daily = fetch_yfinance(tickers, cfg)
        except Exception as exc:
            print(f"price download failed: {exc}", file=sys.stderr)
    if pc is None:
        if not args.offline and (out / "summary.json").exists():
            stale_update(holdings, out, now)
            print("kept previous data, marked as stale")
            return
        # first run without prices: flat series from the last MarketWatch prices
        status, source = "stale", "marketwatch"
        grid = session_grid(to_utc(pd.Timestamp(cfg["start_date"])), now)
        last = {p["ticker"].upper(): float(p.get("last_price") or p.get("avg_cost") or 0) for p in holdings.get("positions", [])}
        for t in txs:
            last.setdefault(t["ticker"], t["price"])
        cols = [t for t in tickers if t in last]
        po = pd.DataFrame({t: last[t] for t in cols}, index=grid)
        pc = po.copy()

    meta = fetch_meta([t for t in tickers if t != bench], load_json(out / "meta_cache.json", {}) or {},
                      cfg, holdings, online=not args.offline and source == "yfinance")
    write_json(out / "meta_cache.json", meta)
    res = compute(cfg, rules, targets, holdings, txs, po, pc, daily, meta, out, now, status=status, price_source=source)
    print(f"fund value {res['nav']:,.2f}  cash {res['cash']:,.2f}  positions {len(res['positions'])}  [{status}]")


if __name__ == "__main__":
    main()
