"""validate.py - out-of-sample tests behind the numbers used in the plan.
    python3 validate.py [live|frozen]      -> output/validation/*.csv and summary.txt
1. Replica: the team's replica study re-tested on the same three test years (Nov 2023-24, 2024-25,
   2025-26) and on 23-day holds, for three constructions.
2. Active-risk model: rolling one-day VaR / ES 97.5% of (book - S&P), four models.
3. Simulator inputs: realised volatility against VIX, square-root-of-time."""
import math, os, sys
import numpy as np
import pandas as pd
from scipy import stats
import config as C
import lib as L
from data import load_prices, pick_source

SRC = pick_source(); OUT = "output/validation"; os.makedirs(OUT, exist_ok=True)
CORE27 = ["NVDA","MSFT","AAPL","AVGO","GOOGL","META","NFLX","AMZN","TSLA","HD","BRK-B","JPM","V","BAC","LLY","JNJ","UNH","ABBV","WMT","PG","COST","XOM","GE","CAT","NEE","LIN","PLD"]
iw = L.replica_names(); U = list(dict.fromkeys(list(iw.index) + list(C.SLEEVE) + CORE27))
P = load_prices(U + [C.BENCH, C.VOL_INDEX], SRC)
R = P[U + [C.BENCH]].pct_change(fill_method=None).iloc[1:]; d = R.index; rm = R[C.BENCH].values; n = len(R); vix = P[C.VOL_INDEX].values[1:] / 100
pd.set_option("display.width", 220); pd.set_option("display.max_columns", 20)
log = open(os.path.join(OUT, "summary.txt"), "w")
def say(*a):
    t = " ".join(str(x) for x in a); print(t); log.write(t + "\n")
say("Validation run:", P.attrs["origin"]); say(f"History: {d[0].date()} to {d[-1].date()} ( {n} days ). Price returns, no dividends.")

# ---- 1. replica constructions ----------------------------------------------------
def fitw(names, t0):
    X = R.iloc[t0 - C.REPLICA_LOOKBACK:t0][names]; ok = [c for c in names if X[c].notna().all()]
    return L.te_min_weights(X[ok], rm[t0 - C.REPLICA_LOOKBACK:t0], C.W_MIN, C.W_MAX)
def fixw(w, t0):
    X = R.iloc[t0 - 250:t0][list(w.index)]; w = w[[c for c in w.index if X[c].notna().all()]]; return w / w.sum()
books = {"A. Index weights (today's), 50 largest ex NVDA": lambda t0: fixw(iw, t0), "B. Min-TE on the same 50 names": lambda t0: fitw(list(iw.index), t0),
         "C. Min-TE on 27 hand-picked names (earlier IGfinal)": lambda t0: fitw(CORE27, t0)}
starts = [int(np.argmax(d >= pd.Timestamp(x))) for x in ("2023-11-13", "2024-11-13", "2025-11-13")]; ends = starts[1:] + [n]
ret = lambda w, a, b: R.iloc[a:b][list(w.index)].values @ w.values
rows = []
for bn, f in books.items():
    yr = []
    for a, b in zip(starts, ends):
        w = f(a); rp = ret(w, a, b); m = rm[a:b]; yr.append((np.cov(rp, m)[0, 1] / np.var(m, ddof=1), L.sd(rp - m) * math.sqrt(252)))
    yr = np.array(yr)
    rows.append({"Portfolio": bn, "Beta, 3 test years": f"{yr[:, 0].mean():.2f} ({' / '.join(f'{x:.2f}' for x in yr[:, 0])})",
                 "Tracking error, %/yr": f"{100 * yr[:, 1].mean():.1f} ({' / '.join(f'{100 * x:.1f}' for x in yr[:, 1])})"})
T1 = pd.DataFrame(rows); say("\n1a. REPLICA, built each November and held for a year (as in the team's replica study)"); say(T1.to_string(index=False))
say("    The study's own figures, with index weights as of each start date: A 0.99 beta / 5.0% TE; free optimiser over 496 names 0.92 / 3.6%.")
say("    Row A here uses TODAY's weights in past years, which overweights past winners and inflates its beta.")
Hh = 23; st = list(range(starts[0], n - Hh, 5)); rows = []
for bn, f in books.items():
    rp, m, l5, l10, dd = [], [], [], [], []
    for s in st:
        w = f(s); a = ret(w, s, s + Hh); mm = rm[s:s + Hh]; cs = np.cumsum(a - mm); rp.append(a); m.append(mm)
        l5.append(cs[:5].min() <= -.005); l10.append(cs[:10].min() <= -.005); dd.append(cs[-1])
    rp, m, dd = np.concatenate(rp), np.concatenate(m), np.array(dd)
    rows.append({"Portfolio": bn, "Beta": round(np.cov(rp, m)[0, 1] / np.var(m, ddof=1), 2), "TE, %/yr": round(100 * L.sd(rp - m) * math.sqrt(252), 1),
                 "23-day gap, 5th pct": round(100 * np.quantile(dd - dd.mean(), .05), 2), "95th pct": round(100 * np.quantile(dd - dd.mean(), .95), 2),
                 "Loses a 0.5% lead within 5 days, %": round(100 * np.mean(l5), 1), "within 10 days, %": round(100 * np.mean(l10), 1)})
T1b = pd.DataFrame(rows); say(f"\n1b. REPLICA, rebuilt on the day and held 23 trading days ({len(st)} windows since Nov 2023)"); say(T1b.to_string(index=False))
T1.to_csv(os.path.join(OUT, "replica_three_test_years.csv"), index=False); T1b.to_csv(os.path.join(OUT, "replica_23_day_holds.csv"), index=False)

# ---- 2. active-risk model backtest ------------------------------------------------
all_nm = list(dict.fromkeys(list(iw.index) + list(C.SLEEVE))); R2 = R.dropna(subset=all_nm); rm2 = R2[C.BENCH].values; n2 = len(R2)
w_rep = iw / iw.sum()
bk = {"Replica (index weights)": L.combine_weights(w_rep, L.build_sleeve_overlay(w_rep, C.SLEEVE, 0), 1),
      "70% replica + 30% sleeve": L.combine_weights(w_rep, L.build_sleeve_overlay(w_rep, C.SLEEVE, C.SLEEVE_SIZE), 1)}
a = C.CONF; WN = min(C.RISK_WINDOW, n2 // 2); qn, qt4 = stats.norm.ppf(a), stats.t.ppf(a, 4)
def kup(h):
    x, Tn, p = h.sum(), len(h), 1 - a; ph = max(x, .5) / Tn
    return 1 - stats.chi2.cdf(-2 * (x * math.log(p) + (Tn - x) * math.log(1 - p) - x * math.log(ph) - (Tn - x) * math.log(1 - ph)), 1)
rows = []; active = {}
for bn, w in bk.items():
    Ls = -(R2[list(w.index)].values @ w.values - rm2); active[bn] = Ls; sg = L.ewma_sigma(Ls, C.LAMBDA); F = []
    for t in range(WN, n2):
        x = Ls[t - WN:t]; z = x / sg[t - WN:t]
        F.append([L.sd(x) * math.sqrt(.5) * qt4, L.ES_t4_reference(x, a), L.VaR_hist(x, a), L.ES_hist(x, a), sg[t] * L.VaR_hist(z, a), sg[t] * L.ES_hist(z, a),
                  sg[t] * qn, sg[t] * stats.norm.pdf(qn) / (1 - a)])
    F = np.array(F); Lo = Ls[WN:]
    for j, nm in enumerate(["Student-t(4), static (reference code)", "Historical, static", "Filtered historical (in use)", "EWMA normal"]):
        v, e = F[:, 2 * j], F[:, 2 * j + 1]; h = Lo > v
        rows.append({"Book": bn, "Model": nm, "Breaches": int(h.sum()), "Expected": round(len(h) * (1 - a), 1), "Kupiec p": round(kup(h), 3),
                     "Z2 (0 = ES right, <0 = too high)": round(float(np.sum(Lo * h / e) / (len(h) * (1 - a)) - 1), 2)})
T2 = pd.DataFrame(rows)
say(f"\n2. ACTIVE-RISK MODELS: one-day VaR / ES {100 * a:.1f}% of (book - S&P), window {WN} days, {n2 - WN} out-of-sample days (history common to all names starts {R2.index[0].date()})")
say(T2.to_string(index=False)); T2.to_csv(os.path.join(OUT, "active_risk_backtest.csv"), index=False)

# ---- 3. simulator inputs -----------------------------------------------------------
idx = range(0, n - 28, 5); ratio = np.array([L.sd(rm[i + 1:i + 29]) * math.sqrt(252) / vix[i] for i in idx])
Ls = active["70% replica + 30% sleeve"]; k5 = range(n2 % 5, n2 - 4, 5); L5 = np.array([Ls[i:i + 5].sum() for i in k5])
T3 = pd.DataFrame({"Check": ["Realised 28-day volatility / VIX, median", "Realised 28-day volatility / VIX, mean", "Active return: 5-day sd / (sqrt(5) x daily sd)", "Active return: lag-1 autocorrelation"],
                   "Value": np.round([np.median(ratio), ratio.mean(), L.sd(L5) / (math.sqrt(5) * L.sd(Ls)), np.corrcoef(Ls[1:], Ls[:-1])[0, 1]], 3)})
say("\n3. SIMULATOR INPUTS"); say(T3.to_string(index=False)); T3.to_csv(os.path.join(OUT, "simulator_inputs.csv"), index=False); log.close()
