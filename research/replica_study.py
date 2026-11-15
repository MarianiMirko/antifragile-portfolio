"""Which is the most efficient way to hold the S&P 500 without buying all its companies?

A walk-forward test on the fund's database. At the end of every month from the start date a
portfolio is built with what was known that day, held for the following month (the length of
the game) and compared with the S&P 500 total-return index. Nothing is fitted on the days
on which it is measured.

Ways of building the portfolio
    A<N>     the N largest companies at their index weights (the replica study's choice)
    A<N>x    the same without NVIDIA
    EW50x    the 50 largest without NVIDIA, equal weights
    S<N>x    N companies spread over the sectors: each sector keeps its index weight and is
             represented by its largest companies (without NVIDIA)
    M50x     the 50 largest without NVIDIA, weights that minimise tracking error (0.5% to 15% per name)
    B50x     the same companies, minimum tracking error with estimated beta forced to 1 (0 to 15%)
    C50x     A50x held in the proportion 1 / estimated beta, the rest in cash (never above 100%)

Index weights in the past are not in the database. They are rebuilt from today's weights and the
price change since then (same number of shares), which ignores buybacks and, because the
database holds dividend-adjusted prices, understates the past weight of high-dividend companies.
The universe is today's index members, so companies that left the index are missing.

    python research/replica_study.py            needs SUPABASE_URL and SUPABASE_SECRET_KEY
    RESEARCH_TEST=prices.csv python research/replica_study.py     smoke test on a local file
"""
import json
import math
import sys

import numpy as np
import pandas as pd
from scipy import optimize

import common as K

START = "2017-01-01"          # first formation month
HISTORY_FROM = "2014-06-01"   # two years of returns before the first formation
LOOKBACK = 504
EXCLUDE = ["NVDA"]
SIZES = [10, 20, 30, 40, 50, 75, 100, 150, 200]


# ---------------------------------------------------------------- optimisers
def min_te(R, rm, lo, hi, beta_one=False):
    """Weights minimising Var(w'R - rm), sum 1, lo <= w <= hi; optionally with estimated beta = 1."""
    X = R.values; n = X.shape[1]
    S = np.cov(X, rowvar=False) + 1e-10 * np.eye(n)
    c = np.array([np.cov(X[:, j], rm)[0, 1] for j in range(n)])
    sc = 1.0 / np.mean(np.diag(S))
    cons = [{"type": "eq", "fun": lambda w: w.sum() - 1, "jac": lambda w: np.ones(n)}]
    if beta_one:
        b = c / np.var(rm, ddof=1)
        cons.append({"type": "eq", "fun": lambda w: w @ b - 1, "jac": lambda w: b})
    w0 = np.clip(np.full(n, 1 / n), lo, hi); w0 /= w0.sum()
    o = optimize.minimize(lambda w: sc * (w @ S @ w - 2 * w @ c), w0, jac=lambda w: sc * (2 * S @ w - 2 * c), method="SLSQP",
                          bounds=[(lo, hi)] * n, constraints=cons, options={"ftol": 1e-12, "maxiter": 1000})
    if not o.success:
        return None
    w = np.maximum(o.x, 0)
    return pd.Series(w / w.sum(), index=R.columns)


def stratified(w, sectors, n, exclude):
    """n companies over the sectors: every sector keeps its index weight, carried by its largest members."""
    sec = sectors.reindex(w.index).fillna("Other"); W = w.groupby(sec).sum()
    raw = W * n; slots = np.maximum(1, np.floor(raw)).astype(int)
    while slots.sum() > n:                              # too many because of the one-per-sector minimum
        k = (slots[slots > 1] - raw[slots > 1]).idxmax(); slots[k] -= 1
    for k in (raw - slots).sort_values(ascending=False).index:
        if slots.sum() >= n:
            break
        slots[k] += 1
    out = {}
    for s, k in slots.items():
        m = w[(sec == s) & ~w.index.isin(exclude)].sort_values(ascending=False).head(k)
        if len(m):
            out.update((m / m.sum() * W[s]).to_dict())
    out = pd.Series(out); return out / out.sum()


# ---------------------------------------------------------------- statistics
def stats(rp, rb, gaps, bench_m):
    d = rp - rb; years = sorted(set(rp.index.year))
    by_year = {}
    for y in years:
        a, b = rp[rp.index.year == y], rb[rb.index.year == y]
        if len(a) > 60:
            by_year[int(y)] = {"beta": float(np.cov(a, b)[0, 1] / np.var(b, ddof=1)), "te": float((a - b).std(ddof=1) * math.sqrt(252))}
    betas = [v["beta"] for v in by_year.values()]
    up = gaps[bench_m > 0.03]; down = gaps[bench_m < -0.03]
    return {
        "beta": float(np.cov(rp, rb)[0, 1] / np.var(rb, ddof=1)),
        "beta_up_days": float(np.cov(rp[rb > 0], rb[rb > 0])[0, 1] / np.var(rb[rb > 0], ddof=1)),
        "beta_down_days": float(np.cov(rp[rb < 0], rb[rb < 0])[0, 1] / np.var(rb[rb < 0], ddof=1)),
        "beta_year_min": float(min(betas)), "beta_year_max": float(max(betas)),
        "beta_abs_error_by_year": float(np.mean([abs(b - 1) for b in betas])),
        "te": float(d.std(ddof=1) * math.sqrt(252)), "corr": float(np.corrcoef(rp, rb)[0, 1]),
        "excess_ann": float(d.mean() * 252),
        "month_gap_p05": float(gaps.quantile(.05)), "month_gap_median": float(gaps.median()), "month_gap_p95": float(gaps.quantile(.95)),
        "month_gap_beyond_1pt": float((gaps.abs() > 0.01).mean()),
        "gap_when_index_up_3": float(up.mean()) if len(up) else None, "gap_when_index_down_3": float(down.mean()) if len(down) else None,
        "months": int(len(gaps)), "by_year": by_year,
    }


# ---------------------------------------------------------------- main
def main():
    if K.TEST_FILE:
        allp = K.test_prices(); bench = allp["^GSPC"].dropna(); px = allp.drop(columns=[c for c in allp.columns if c.startswith("^")])
        iw = pd.read_csv(K.ROOT / "models/igfinal/input/sp500_index_weights.csv"); iw = iw.set_index("ticker")["sp500_weight_pct"]
        w_today = iw.reindex(px.columns).dropna(); w_today /= w_today.sum(); w_source = "test file"
        px = px[w_today.index]; sectors = pd.Series({t: "S" + str(i % 5) for i, t in enumerate(px.columns)}); bench_name = "^GSPC (test)"
        sizes = [10, 20, 30, 50]
    else:
        px, sec = K.db_prices(HISTORY_FROM)
        y = K.yahoo(["^SP500TR"], HISTORY_FROM, fields=("Close",))["Close"]["^SP500TR"].dropna()
        bench, bench_name = y, "S&P 500 total return index (^SP500TR, Yahoo Finance)"
        for a, b in (("GOOGL", "GOOG"), ("FOXA", "FOX"), ("NWSA", "NWS")):           # one company, two lines
            if a in px.columns and b in px.columns:
                px = px.drop(columns=b)
        w_today, w_source = K.index_weights(list(px.columns))
        px = px[w_today.index]; sectors = sec["sector"]; sizes = SIZES

    days = px.index.intersection(bench.index); px = px.loc[days].ffill(limit=5); bench = bench.loc[days]
    R = px.pct_change(); rb_all = bench.pct_change()
    shares = w_today / px.ffill().iloc[-1]                 # same number of shares through time
    cap = px * shares                                       # relative market value, day by day

    month_end = [pd.Timestamp(d) for d in pd.Series(days, index=days).groupby([days.year, days.month]).max().values]
    if month_end[-1] != days[-1]:
        month_end.append(days[-1])                          # the running month ends at the last price
    nxt = dict(zip(month_end[:-1], month_end[1:]))          # formation day -> last day of the holding month
    forms = [d for d in month_end[:-1] if d >= pd.Timestamp(START) - pd.Timedelta(days=5) and days.get_loc(d) >= LOOKBACK]
    K.log(f"{len(forms)} monthly portfolios from {pd.Timestamp(forms[0]).date()} to {pd.Timestamp(forms[-1]).date()}; benchmark {bench_name}")

    series, gaps, bench_m, n_names, expo, failed = {}, {}, {}, {}, {}, {}
    last_weights = {}
    for f in forms:
        p = days.get_loc(f); hold = days[p + 1:days.get_loc(nxt[f]) + 1]
        if len(hold) < 5:
            continue
        c = cap.iloc[p].dropna(); c = c[px.iloc[p - 252][c.index].notna()]        # listed for at least a year
        w = c / c.sum(); wx = w.drop(labels=[t for t in EXCLUDE if t in w.index])
        ports = {}
        for n in sizes:
            if n <= len(w):
                t = w.sort_values(ascending=False).head(n); ports[f"A{n}"] = t / t.sum()
            if n <= len(wx):
                t = wx.sort_values(ascending=False).head(n); ports[f"A{n}x"] = t / t.sum()
        top50 = wx.sort_values(ascending=False).head(50)
        ports["A50x"] = top50 / top50.sum()
        ports["EW50x"] = pd.Series(1 / len(top50), index=top50.index)
        for n in (50, 100):
            if n < len(wx):
                ports[f"S{n}x"] = stratified(w, sectors, n, EXCLUDE)
        win = R.iloc[p - LOOKBACK + 1:p + 1]; rmw = rb_all.iloc[p - LOOKBACK + 1:p + 1].values
        ok = [t for t in top50.index if win[t].notna().all()]
        for name, kw in (("M50x", dict(lo=0.005, hi=0.15)), ("B50x", dict(lo=0.0, hi=0.15, beta_one=True))):
            wopt = min_te(win[ok], rmw, **kw)
            if wopt is None:
                failed[name] = failed.get(name, 0) + 1; wopt = ports["A50x"]          # optimiser gave up: hold index weights that month
            ports[name] = wopt
        a50 = ports["A50x"]; known = a50[ok] / a50[ok].sum()          # beta estimated on the names with a full history
        hist = (win[ok] * known).sum(axis=1)
        b_est = float(np.cov(hist.values, rmw)[0, 1] / np.var(rmw, ddof=1))
        ports["C50x"] = a50 * min(1.0, 1.0 / b_est)

        rel = px.loc[hold] / px.iloc[p]                      # growth of one dollar in each stock since formation
        rbh = rb_all.loc[hold]; bm = float((1 + rbh).prod() - 1)
        for name, wts in ports.items():
            cash = 1 - wts.sum()
            v = (rel[wts.index] * wts).sum(axis=1) + cash
            r = v.pct_change(); r.iloc[0] = v.iloc[0] - 1
            series.setdefault(name, []).append(r); gaps.setdefault(name, []).append(float(v.iloc[-1] - 1) - bm)
            n_names.setdefault(name, []).append(int((wts > 0).sum())); expo.setdefault(name, []).append(float(wts.sum()))
            last_weights[name] = wts
        bench_m[f] = bm

    def clean(o):
        if isinstance(o, dict):
            return {k: clean(v) for k, v in o.items()}
        if isinstance(o, float) and not math.isfinite(o):
            return None
        return o

    bm = pd.Series(bench_m); out = {}
    for name in series:
        rp = pd.concat(series[name]); rb = rb_all.loc[rp.index]
        g = pd.Series(gaps[name], index=bm.index)
        s = stats(rp, rb, g, bm); s["names"] = float(np.mean(n_names[name])); s["equity_share"] = float(np.mean(expo[name]))
        s["optimiser_failures"] = failed.get(name, 0)
        # the three years of the team's replica study, for comparison
        m = (rp.index >= "2023-11-15") & (rp.index <= "2026-11-13")
        if m.sum() > 200:
            s["study_period"] = {"beta": float(np.cov(rp[m], rb[m])[0, 1] / np.var(rb[m], ddof=1)), "te": float((rp[m] - rb[m]).std(ddof=1) * math.sqrt(252))}
        out[name] = s

    K.RESULTS.mkdir(exist_ok=True)
    meta = {"generated": pd.Timestamp.now("UTC").isoformat(timespec="seconds"), "benchmark": bench_name, "weights_source": w_source,
            "first_portfolio": str(pd.Timestamp(forms[0]).date()), "last_portfolio": str(pd.Timestamp(forms[-1]).date()), "portfolios": len(forms),
            "stocks_in_universe": int(px.shape[1]), "excluded": EXCLUDE, "lookback_days": LOOKBACK, "last_price_date": str(days[-1].date()),
            "coverage_top50_ex_nvda_today": float(w_today.drop(labels=[t for t in EXCLUDE if t in w_today.index]).sort_values(ascending=False).head(50).sum()),
            "nvda_weight_today": float(w_today.get("NVDA", np.nan))}
    (K.RESULTS / "replica_study.json").write_text(json.dumps(clean({"meta": meta, "methods": out}), indent=1, allow_nan=False))

    # curve for the site's Backtest page: the replica to buy against the index, both rebased to 100
    rp = pd.concat(series["A50x"]); rb = rb_all.loc[rp.index]
    eq = pd.DataFrame({"strategy": 100 * (1 + rp).cumprod(), "benchmark": 100 * (1 + rb).cumprod()})
    eq = eq.resample("W-FRI").last().dropna().round(2); eq.index.name = "date"
    eq.to_csv(K.RESULTS / "replica_A50x_curve.csv")
    pd.DataFrame({k: v for k, v in last_weights.items() if k in ("A50x", "M50x", "B50x", "S50x", "C50x")}).round(5).to_csv(K.RESULTS / "replica_latest_weights.csv")

    # the portfolios one would buy today (last price in the database), and how each spreads over the sectors
    c = cap.iloc[-1].dropna(); c = c[px.iloc[-253][c.index].notna()]; w = c / c.sum(); wx = w.drop(labels=[t for t in EXCLUDE if t in w.index])
    a = wx.sort_values(ascending=False).head(50); a = a / a.sum(); sx = stratified(w, sectors, 50, EXCLUDE)
    today = pd.DataFrame({"sector": sectors.reindex(w.index), "index_weight": w, "A50x": a, "S50x": sx})
    today = today[today[["A50x", "S50x"]].notna().any(axis=1)].sort_values("index_weight", ascending=False)
    today.index.name = "ticker"; today.round(5).to_csv(K.RESULTS / "replica_today.csv")
    sec_tab = pd.DataFrame({"index": w.groupby(sectors.reindex(w.index)).sum(), "A50x": a.groupby(sectors.reindex(a.index)).sum(),
                            "S50x": sx.groupby(sectors.reindex(sx.index)).sum()}).fillna(0).sort_values("index", ascending=False)
    sec_tab.index.name = "sector"; sec_tab.round(4).to_csv(K.RESULTS / "replica_sectors_today.csv")
    K.log("\nSector weights today (index | 50 largest ex NVDA | 50 spread over sectors):")
    for r in sec_tab.itertuples():
        K.log(f"  {r.Index:26s} {100 * r.index:5.1f}%  {100 * r.A50x:5.1f}%  {100 * r.S50x:5.1f}%")

    cols = ["names", "beta", "beta_year_min", "beta_year_max", "te", "month_gap_p05", "month_gap_p95", "month_gap_beyond_1pt", "gap_when_index_up_3"]
    K.log("\n" + f"{'method':8s} names  beta  [yr min..max]   TE    month gap 5%..95%   >1pt   gap when index >+3%")
    for name, s in out.items():
        K.log(f"{name:8s} {s['names']:5.0f}  {s['beta']:.3f} [{s['beta_year_min']:.2f}..{s['beta_year_max']:.2f}]  {100 * s['te']:4.1f}%   "
              f"{100 * s['month_gap_p05']:+5.2f}..{100 * s['month_gap_p95']:+5.2f}      {100 * s['month_gap_beyond_1pt']:3.0f}%   "
              f"{'' if s['gap_when_index_up_3'] is None else format(100 * s['gap_when_index_up_3'], '+.2f')}"
              + (f"   | study years: beta {s['study_period']['beta']:.2f} TE {100 * s['study_period']['te']:.1f}%" if "study_period" in s else ""))
    if failed:
        K.log("optimiser failures (index weights held instead):", failed)


if __name__ == "__main__":
    sys.exit(main())
