"""How did the listed "friends" of a company move around its IPO?

For every large technology IPO in research/ipo_events.csv and every listed company tied to it
(a shareholder, a buyer of shares alongside the IPO, the parent, a dominant customer) the script
measures the return of the friend over the window the fund plans to use for the Anthropic IPO:

    buy at the open three trading days before the first trading day (our Monday)
    sell at the open of the first trading day                         (our Thursday)

and compares it with the S&P 500 (SPY) over the same hours. It also looks at what happened
before that window and after it, to judge the entry and the exit.

A second, broader test asks whether technology stocks as a group (XLK, QQQ) beat the market
around the 37 large technology IPOs in research/ipo_dates_broad.csv.

Opening prices are not in the fund's database, so prices come from Yahoo Finance (adjusted for
splits and dividends). Where a friend is in the database, its closes are checked against it.

    python research/ipo_event_study.py
    RESEARCH_TEST=prices.csv python research/ipo_event_study.py     smoke test on a local file
"""
import json
import math
import sys

import numpy as np
import pandas as pd
from scipy import stats as st

import common as K

ENTRY = 3            # trading days before the first trading day
WINDOWS = {          # name: (from price, from offset, to price, to offset), offsets in trading days from the first trading day
    "plan": ("O", -ENTRY, "O", 0),                 # Monday open -> Thursday open
    "to_close_day_before": ("O", -ENTRY, "C", -1),  # Monday open -> Wednesday close
    "to_close_ipo_day": ("O", -ENTRY, "C", 0),      # Monday open -> Thursday close
    "two_weeks_before_entry": ("C", -ENTRY - 11, "C", -ENTRY - 1),
    "ipo_day": ("O", 0, "C", 0),
    "week_after_exit": ("O", 0, "C", 5),
    "month_after_exit": ("O", 0, "C", 20),
}


def window_return(o, c, pos, spec):
    a, i, b, j = spec
    if pos + i < 0 or pos + j >= len(c):
        return np.nan
    p0 = (o if a == "O" else c).iloc[pos + i]; p1 = (o if b == "O" else c).iloc[pos + j]
    return float(p1 / p0 - 1) if p0 > 0 and p1 > 0 else np.nan


def summary(df, col, rng):
    """Pair-level and IPO-level statistics of one abnormal-return column (IPO level: friends of the same IPO averaged first)."""
    x = df[col].dropna()
    if len(x) < 3:
        return None
    g = df.dropna(subset=[col]).groupby("ipo")[col].mean(); n = len(g)
    boot = [g.sample(n, replace=True, random_state=int(rng.integers(1 << 31))).mean() for _ in range(5000)]
    wins = int((g > 0).sum())
    return {"pairs": int(len(x)), "pair_mean": float(x.mean()), "pair_median": float(x.median()), "pair_share_positive": float((x > 0).mean()),
            "ipos": int(n), "ipo_mean": float(g.mean()), "ipo_median": float(g.median()), "ipo_share_positive": wins / n,
            "t_stat": float(g.mean() / (g.std(ddof=1) / math.sqrt(n))) if n > 2 and g.std(ddof=1) > 0 else None,
            "p_value": float(2 * st.t.sf(abs(g.mean() / (g.std(ddof=1) / math.sqrt(n))), n - 1)) if n > 2 and g.std(ddof=1) > 0 else None,
            "ci95_low": float(np.quantile(boot, .025)), "ci95_high": float(np.quantile(boot, .975)),
            "sign_test_p": float(st.binomtest(wins, n, 0.5).pvalue), "best": float(g.max()), "worst": float(g.min())}


def main():
    ev = pd.read_csv(K.HERE / "ipo_events.csv", parse_dates=["first_trading_day"])
    broad = pd.read_csv(K.HERE / "ipo_dates_broad.csv", parse_dates=["first_trading_day"])
    friends = sorted(set(ev.friend)); extra = ["SPY", "XLK", "QQQ"]
    if K.TEST_FILE:
        allp = K.test_prices().rename(columns={"^GSPC": "SPY"}); C = allp[[c for c in allp.columns if not c.startswith("^")]].copy()
        C.columns = [c.replace(".", "-") for c in C.columns]; O = C.shift(1)       # no opens in the test file: yesterday's close stands in
        ev = ev[ev.friend.isin(C.columns) & (ev.first_trading_day > C.index[300])]
        broad = broad[broad.first_trading_day > C.index[300]]; db = None
    else:
        y = K.yahoo(friends + extra, "2003-06-01"); O, C = y["Open"], y["Close"]
        try:
            db, _ = K.db_prices("2006-01-01", tickers=[f.replace("-", ".") for f in friends])
            db.columns = [c.replace(".", "-") for c in db.columns]
        except Exception as exc:
            K.log(f"database check skipped: {type(exc).__name__}: {exc}"); db = None
    cal = C["SPY"].dropna().index; O, C = O.reindex(cal), C.reindex(cal)
    rng = np.random.default_rng(7)

    rows, checks = [], []
    for e in ev.itertuples():
        if e.first_trading_day not in cal:
            K.log(f"{e.ipo}: {e.first_trading_day.date()} is not a trading day, skipped"); continue
        pos = cal.get_loc(e.first_trading_day); f = e.friend
        if f not in C.columns or pd.isna(C[f].iloc[max(pos - 270, 0)]) or pd.isna(O[f].iloc[pos - ENTRY]):
            K.log(f"{e.ipo} / {f}: no price history around the IPO, skipped"); continue
        row = {"ipo": e.ipo, "date": str(e.first_trading_day.date()), "friend": f, "tier": int(e.tier), "link": e.link}
        d = C[[f, "SPY"]].pct_change().iloc[pos - 260:pos - 10].dropna()
        beta = float(np.cov(d[f], d["SPY"])[0, 1] / np.var(d["SPY"], ddof=1)); row["beta"] = beta
        for name, spec in WINDOWS.items():
            r, m = window_return(O[f], C[f], pos, spec), window_return(O["SPY"], C["SPY"], pos, spec)
            row[name] = r; row[name + "_spy"] = m; row[name + "_vs_spy"] = r - m; row[name + "_beta_adj"] = r - beta * m
        # the same three-day window on every other day of the year before: is the IPO window unusual for this stock?
        s = np.arange(pos - 263, pos - 13)
        pl = (O[f].values[s + ENTRY] / O[f].values[s] - 1) - (O["SPY"].values[s + ENTRY] / O["SPY"].values[s] - 1)
        pl = pl[np.isfinite(pl)]
        row["placebo_mean"] = float(pl.mean()); row["placebo_sd"] = float(pl.std(ddof=1))
        row["plan_z"] = float((row["plan_vs_spy"] - pl.mean()) / pl.std(ddof=1))
        row["plan_percentile"] = float((pl < row["plan_vs_spy"]).mean())
        if db is not None and f in db.columns:
            dc = db[f].reindex(cal)
            a = dc.iloc[pos - 1] / dc.iloc[pos - ENTRY - 1] - 1; b = C[f].iloc[pos - 1] / C[f].iloc[pos - ENTRY - 1] - 1
            if np.isfinite(a) and np.isfinite(b):
                checks.append(abs(a - b)); row["db_close_to_close_vs_spy"] = float(a - (C["SPY"].iloc[pos - 1] / C["SPY"].iloc[pos - ENTRY - 1] - 1))
        rows.append(row)
    df = pd.DataFrame(rows)

    groups = {"all": df, "strong_link": df[df.tier == 1], "weak_link": df[df.tier == 2], "since_2023": df[df.date >= "2023-01-01"]}
    out = {g: {w: summary(d, w + "_vs_spy", rng) for w in WINDOWS} | {"plan_beta_adjusted": summary(d, "plan_beta_adj", rng),
                                                                     "plan_z": summary(d, "plan_z", rng)} for g, d in groups.items()}
    per_ipo = df.groupby(["ipo", "date"]).agg(friends=("friend", lambda s: ", ".join(s)), plan=("plan_vs_spy", "mean"), raw=("plan", "mean"),
                                                 market=("plan_spy", "mean"), before=("two_weeks_before_entry_vs_spy", "mean"),
                                                 ipo_day=("ipo_day_vs_spy", "mean"), week_after=("week_after_exit_vs_spy", "mean"),
                                                 month_after=("month_after_exit_vs_spy", "mean")).reset_index().sort_values("date")

    # technology as a group around the broader list of IPOs
    sector = []
    for e in broad.itertuples():
        if e.first_trading_day not in cal:
            continue
        pos = cal.get_loc(e.first_trading_day); r = {"ipo": e.ipo, "date": str(e.first_trading_day.date())}
        for etf in ("XLK", "QQQ"):
            if etf in C.columns and pos - ENTRY - 12 >= 0 and not pd.isna(O[etf].iloc[pos - ENTRY - 12]):
                for name, spec in WINDOWS.items():
                    r[f"{etf}_{name}"] = window_return(O[etf], C[etf], pos, spec) - window_return(O["SPY"], C["SPY"], pos, spec)
        sector.append(r)
    sec = pd.DataFrame(sector)
    sec_out = {c: summary(sec.rename(columns={c: "x"}).assign(ipo=sec.ipo), "x", rng) for c in sec.columns if c not in ("ipo", "date")}

    K.RESULTS.mkdir(exist_ok=True)

    def clean(o):
        if isinstance(o, dict):
            return {k: clean(v) for k, v in o.items()}
        if isinstance(o, list):
            return [clean(v) for v in o]
        if isinstance(o, float) and not math.isfinite(o):
            return None
        return o
    meta = {"generated": pd.Timestamp.now("UTC").isoformat(timespec="seconds"), "ipos": int(df.ipo.nunique()), "pairs": int(len(df)),
            "entry": f"open {ENTRY} trading days before the first trading day", "exit": "open of the first trading day",
            "market": "SPY, same hours", "database_check_max_difference": float(max(checks)) if checks else None,
            "database_check_pairs": len(checks), "last_price_date": str(cal[-1].date())}
    (K.RESULTS / "ipo_event_study.json").write_text(json.dumps(clean({"meta": meta, "friends": out, "per_ipo": per_ipo.to_dict("records"),
                                                                     "technology_sector": sec_out}), indent=1, allow_nan=False))
    df.round(5).to_csv(K.RESULTS / "ipo_event_pairs.csv", index=False)
    sec.round(5).to_csv(K.RESULTS / "ipo_event_sector.csv", index=False)

    K.log(f"\n{meta['ipos']} IPOs, {meta['pairs']} friend-IPO pairs. Database check on {len(checks)} pairs: max difference "
          f"{'n/a' if not checks else format(100 * max(checks), '.3f') + ' points'}")
    K.log("\nFriends minus S&P 500, averaged per IPO   (mean | median | share > 0 | t | p | 95% interval)")
    for g, res in out.items():
        K.log(f" {g}")
        for w, s in res.items():
            if s and w != "plan_z":
                K.log(f"   {w:26s} n={s['ipos']:2d}  {100 * s['ipo_mean']:+6.2f}% | {100 * s['ipo_median']:+6.2f}% | {100 * s['ipo_share_positive']:3.0f}% | "
                      f"t {s['t_stat']:+.2f} | p {s['p_value']:.2f} | {100 * s['ci95_low']:+.2f}..{100 * s['ci95_high']:+.2f}")
        if res.get("plan_z"):
            K.log(f"   plan window against the stock's own ordinary three-day moves: mean z {res['plan_z']['ipo_mean']:+.2f} (p {res['plan_z']['p_value']:.2f})")
    K.log("\nPer IPO (friends minus S&P 500): plan window | two weeks before | IPO day | week after | month after")
    for r in per_ipo.itertuples():
        K.log(f" {r.date} {r.ipo:12s} {100 * r.plan:+6.2f}% | {100 * r.before:+6.2f}% | {100 * r.ipo_day:+6.2f}% | {100 * r.week_after:+6.2f}% | "
              f"{'' if pd.isna(r.month_after) else format(100 * r.month_after, '+6.2f') + '%'}   [{r.friends}]")
    K.log("\nTechnology funds minus S&P 500 around the broader list of IPOs")
    for c, s in sec_out.items():
        if s:
            K.log(f"   {c:32s} n={s['ipos']:2d}  mean {100 * s['ipo_mean']:+5.2f}% | median {100 * s['ipo_median']:+5.2f}% | >0 {100 * s['ipo_share_positive']:3.0f}% | t {s['t_stat']:+.2f} | p {s['p_value']:.2f}")


if __name__ == "__main__":
    sys.exit(main())
