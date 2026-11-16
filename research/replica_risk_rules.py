"""Riccardo's replica with the risk rules of Lorenzo's allocation model (models/igfinal/config.py).

Called at the end of replica_study.py with the data it has already loaded, so it uses the same
prices, the same monthly portfolios and the same benchmark. Three versions, rebuilt every month
with what was known that day and held for the following month:

    A50x     Riccardo: the 50 largest companies without NVIDIA at index weights (no extra rule)
    L1       the same with Lorenzo's position limit: no name above 15% (the excess is shared
             among the other names in proportion to their weight)
    L2       L1, and every month the model's active-risk check: 5-day 97.5% expected shortfall of
             (replica - S&P 500), historical on 504 days with scenarios rescaled to today's EWMA
             volatility (lambda 0.94), square root of time. When it is above the replica limit
             (3%), that month the replica is held at the model's minimum-tracking-error weights
             (same 50 names, 0.5% to 15% each), which is how the model brings active risk down.

Other rules of the model do not change a pure replica: at most 60 names (we hold 50), no short
positions, no margin, always 100% invested (portfolio manager, 15 Nov).
"""
import json
import math

import numpy as np
import pandas as pd

import common as K

CAP = 0.15
ES_LIMIT = 0.03
CONF, HORIZON, WINDOW, LAMBDA = 0.975, 5, 504, 0.94


def cap_weights(w, cap=CAP):
    w = w.copy()
    for _ in range(50):
        over = w > cap + 1e-12
        if not over.any():
            break
        excess = float((w[over] - cap).sum()); w[over] = cap
        free = ~over & (w < cap)
        w[free] += excess * w[free] / w[free].sum()
    return w / w.sum()


def es_hist(losses, a=CONF):
    x = np.sort(np.asarray(losses, float))[::-1]; k = len(x) * (1 - a); kf = int(math.floor(k + 1e-9))
    s = x[:kf].sum() + (x[kf] * (k - kf) if k - kf > 1e-9 and kf < len(x) else 0.0)
    return float(s / k)


def active_es(win, rb, w):
    """Lorenzo's estimator on the active return of weights w against the benchmark."""
    names = [t for t in w.index if win[t].notna().all()]
    ww = w[names] / w[names].sum()
    d = (win[names].values @ ww.values) - rb
    v = np.empty(len(d)); v[0] = d[:20].var()
    for i in range(1, len(d)):
        v[i] = LAMBDA * v[i - 1] + (1 - LAMBDA) * d[i - 1] ** 2
    sig = np.sqrt(v); now = math.sqrt(LAMBDA * v[-1] + (1 - LAMBDA) * d[-1] ** 2)
    scen = d * now / np.maximum(sig, 1e-12)
    return es_hist(-scen) * math.sqrt(HORIZON)


def max_dd(r):
    v = (1 + r).cumprod(); return float((v / v.cummax() - 1).min())


def summary(rp, rb, gaps):
    d = rp - rb; yrs = len(rp) / 252
    out = {
        "annual_return": float((1 + rp).prod() ** (1 / yrs) - 1), "benchmark_annual_return": float((1 + rb).prod() ** (1 / yrs) - 1),
        "volatility": float(rp.std(ddof=1) * math.sqrt(252)), "max_drawdown": max_dd(rp), "benchmark_max_drawdown": max_dd(rb),
        "beta": float(np.cov(rp, rb)[0, 1] / np.var(rb, ddof=1)), "tracking_error": float(d.std(ddof=1) * math.sqrt(252)),
        "month_gap_p05": float(gaps.quantile(.05)), "month_gap_p95": float(gaps.quantile(.95)),
        "months_beating_index_by_1_88": float((gaps >= 0.0188).mean()), "months_trailing_index_by_1_88": float((gaps <= -0.0188).mean()),
        "months_ahead_of_index": float((gaps > 0).mean()),
        "by_year": {},
    }
    for y in sorted(set(rp.index.year)):
        a, b = rp[rp.index.year == y], rb[rb.index.year == y]
        out["by_year"][int(y)] = {"return": float((1 + a).prod() - 1), "benchmark": float((1 + b).prod() - 1),
                                  "beta": float(np.cov(a, b)[0, 1] / np.var(b, ddof=1)) if len(a) > 60 else None}
    return out


def run(px, R, rb_all, cap, days, forms, nxt, exclude, min_te):
    series, gaps, log = {"A50x": [], "L1": [], "L2": []}, {"A50x": [], "L1": [], "L2": []}, []
    for f in forms:
        p = days.get_loc(f); hold = days[p + 1:days.get_loc(nxt[f]) + 1]
        if len(hold) < 5:
            continue
        c = cap.iloc[p].dropna(); c = c[px.iloc[p - 252][c.index].notna()]
        w = c / c.sum(); wx = w.drop(labels=[t for t in exclude if t in w.index])
        top = wx.sort_values(ascending=False).head(50); a50 = top / top.sum()
        l1 = cap_weights(a50)
        win = R.iloc[p - WINDOW + 1:p + 1]; rbw = rb_all.iloc[p - WINDOW + 1:p + 1].values
        es1 = active_es(win, rbw, l1)
        l2, switched = l1, False
        if es1 > ES_LIMIT:
            ok = [t for t in top.index if win[t].notna().all()]
            wopt = min_te(win[ok], rbw, lo=0.005, hi=CAP)
            if wopt is not None:
                l2, switched = wopt, True
        log.append({"month": str(pd.Timestamp(f).date()), "max_weight_riccardo": float(a50.max()), "capped": bool(a50.max() > CAP + 1e-9),
                    "active_es_5d": es1, "breach": bool(es1 > ES_LIMIT), "switched_to_min_te": switched})
        rel = px.loc[hold] / px.iloc[p]; bm = float((1 + rb_all.loc[hold]).prod() - 1)
        for name, wts in (("A50x", a50), ("L1", l1), ("L2", l2)):
            v = (rel[wts.index] * wts).sum(axis=1) + (1 - wts.sum())
            r = v.pct_change(); r.iloc[0] = v.iloc[0] - 1
            series[name].append(r); gaps[name].append(float(v.iloc[-1] - 1) - bm)
    out = {}
    idx = [pd.Timestamp(m["month"]) for m in log]
    for name in series:
        rp = pd.concat(series[name]); rb = rb_all.loc[rp.index]
        out[name] = summary(rp, rb, pd.Series(gaps[name], index=idx))
    lg = pd.DataFrame(log)
    meta = {"months": len(log), "months_capped": int(lg.capped.sum()), "months_es_breach": int(lg.breach.sum()),
            "months_switched": int(lg.switched_to_min_te.sum()), "es_median": float(lg.active_es_5d.median()),
            "es_max": float(lg.active_es_5d.max()), "es_last": float(lg.active_es_5d.iloc[-1]),
            "max_weight_riccardo_max": float(lg.max_weight_riccardo.max()), "cap": CAP, "es_limit": ES_LIMIT}
    K.RESULTS.mkdir(exist_ok=True)
    (K.RESULTS / "replica_lorenzo_rules.json").write_text(json.dumps({"meta": meta, "versions": out}, indent=1))
    lg.round(5).to_csv(K.RESULTS / "replica_lorenzo_rules_months.csv", index=False)
    K.log(f"Lorenzo's rules: capped {meta['months_capped']} months, ES breach {meta['months_es_breach']}, switched {meta['months_switched']}")
    for name, s in out.items():
        K.log(f"  {name}: {100 * s['annual_return']:.1f}% a year (index {100 * s['benchmark_annual_return']:.1f}%), beta {s['beta']:.2f}, "
              f"TE {100 * s['tracking_error']:.1f}%, max DD {100 * s['max_drawdown']:.1f}%")
