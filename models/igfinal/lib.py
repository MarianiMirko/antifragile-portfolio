"""lib.py - risk measures, Euler / Shapley allocation, replica, sleeve, bonus simulator.
Same estimators as the R version (IGfinal/R/lib.R):
 * every measure is a weighted average of scenarios, rho(L) = sum_t om_t L_t, so the Euler
   contribution of leg i is sum_t om_t X[t, i] and adds up exactly;
 * Shapley is the position game v(S) = rho(sum of the legs in S), computed exactly;
 * risk is conditional: scenarios are rescaled to today's EWMA volatility.
Convention: losses positive."""
import math, warnings
from datetime import timedelta
import numpy as np
import pandas as pd
from scipy import optimize, stats
import config as C


# ---- risk measures -----------------------------------------------------------
def es_weights(x, a):
    x = np.asarray(x, float); n = len(x); k = n * (1 - a)
    o = np.argsort(-x, kind="stable"); om = np.zeros(n); kf = int(math.floor(k + 1e-9))
    om[o[:kf]] = 1.0
    if k - kf > 1e-9:
        om[o[kf]] = k - kf
    return om / k


def ES_hist(x, a):
    x = np.asarray(x, float); return float(np.sum(es_weights(x, a) * x))


def VaR_hist(x, a):                                   # inverse empirical CDF (R quantile type 1)
    x = np.sort(np.asarray(x, float)); return float(x[int(math.ceil(len(x) * a - 1e-9)) - 1])


def sd(x):
    return float(np.std(x, ddof=1))


def ES_normal(x, a):                                  # zero-mean
    return sd(x) * stats.norm.pdf(stats.norm.ppf(a)) / (1 - a)


def expectile(x, tau):
    x = np.asarray(x, float)
    f = lambda m: tau * np.sum(np.maximum(x - m, 0)) - (1 - tau) * np.sum(np.maximum(m - x, 0))
    return float(optimize.brentq(f, x.min(), x.max(), xtol=1e-14))


def fit_t(x):
    """Location-scale Student-t by maximum likelihood. s is the SCALE, not the standard deviation."""
    x = np.asarray(x, float)
    def nll(p):
        s = math.exp(p[1]); nu = 2 + math.exp(p[2])
        return -np.sum(stats.t.logpdf((x - p[0]) / s, nu) - math.log(s))
    o = optimize.minimize(nll, [np.median(x), math.log(sd(x) * .7), math.log(4)], method="BFGS")
    return dict(mu=o.x[0], s=math.exp(o.x[1]), nu=2 + math.exp(o.x[2]))


def ES_t(s, nu, a):
    q = stats.t.ppf(a, nu); return s * stats.t.pdf(q, nu) / (1 - a) * (nu + q * q) / (nu - 1)


def ES_t4_reference(x, a):                            # the measure of the original reference code
    return ES_t(sd(x) * math.sqrt(2 / 4), 4, a)


def ewma_sigma(x, lam, burn=60):
    """Element t is the forecast for day t (data up to t-1); the last element is tomorrow."""
    x = np.asarray(x, float); n = len(x); s2 = np.empty(n + 1); s2[0] = np.var(x[:min(burn, n)], ddof=1)
    for t in range(n):
        s2[t + 1] = lam * s2[t] + (1 - lam) * x[t] ** 2
    return np.sqrt(s2)


def fhs_factors(L, lam=None):
    """Factors that restate each past day at today's volatility (filtered historical simulation)."""
    s = ewma_sigma(L, C.LAMBDA if lam is None else lam); return s[-1] / s[:-1]


def ES_fhs(L, a=None, h=None):
    L = np.asarray(L, float)
    return math.sqrt(C.HORIZON if h is None else h) * ES_hist(L * fhs_factors(L), C.CONF if a is None else a)


# ---- allocation ---------------------------------------------------------------
def shapley_exact(X, rho):
    """X: scenarios x legs. Exact Shapley value of v(S) = rho(sum of the legs in S)."""
    n = X.shape[1]; N = 2 ** n; v = np.zeros(N)
    for m in range(1, N):
        idx = [i for i in range(n) if m >> i & 1]; v[m] = rho(X[:, idx].sum(axis=1))
    phi = np.zeros(n); fn = math.factorial(n)
    for i in range(n):
        for m in range(N):
            if not m >> i & 1:
                s = bin(m).count("1")
                phi[i] += math.factorial(s) * math.factorial(n - s - 1) / fn * (v[m | 1 << i] - v[m])
    return phi


def block_index(n, rng, b=10):
    """Stationary bootstrap indices (blocks of geometric length, mean b)."""
    idx = np.empty(n, int); idx[0] = rng.integers(n); new = rng.random(n) < 1 / b; jump = rng.integers(n, size=n)
    for t in range(1, n):
        idx[t] = jump[t] if new[t] else (idx[t - 1] + 1) % n
    return idx


# ---- replica and sleeve ---------------------------------------------------------
def te_min_weights(R, rm, wmin, wmax):
    """min Var(w'R - rm)  s.t. sum w = 1, wmin <= w <= wmax.  R: DataFrame of returns."""
    X = R.values; n = X.shape[1]; S = np.cov(X, rowvar=False) + 1e-10 * np.eye(n)
    c = np.array([np.cov(X[:, j], rm)[0, 1] for j in range(n)])
    sc = 1.0 / np.mean(np.diag(S))                    # scale the objective for the solver
    f = lambda w: sc * (w @ S @ w - 2 * w @ c); g = lambda w: sc * (2 * S @ w - 2 * c)
    w0 = np.clip(np.full(n, 1 / n), wmin, wmax); w0 /= w0.sum()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")               # SLSQP reports harmless bound clipping
        o = optimize.minimize(f, w0, jac=g, method="SLSQP", bounds=[(wmin, wmax)] * n,
                              constraints=[{"type": "eq", "fun": lambda w: w.sum() - 1, "jac": lambda w: np.ones(n)}],
                              options={"ftol": 1e-14, "maxiter": 2000})
    if not o.success:
        raise RuntimeError("Replica optimisation did not converge: " + o.message)
    w = np.maximum(o.x, 0); return pd.Series(w / w.sum(), index=R.columns)


def replica_names():
    iw = pd.read_csv(C.INDEX_WEIGHTS_FILE); iw["ticker"] = iw["ticker"].str.replace(".", "-", regex=False)
    iw = iw[~iw["ticker"].isin(C.REPLICA_EXCLUDE)].head(C.REPLICA_N)
    return pd.Series(iw["sp500_weight_pct"].values, index=iw["ticker"].values, dtype=float)


def replica_weights(method, R, rm):
    iw = replica_names(); iw = iw[[t for t in iw.index if t in R.columns]]
    if method == "index":
        return iw / iw.sum()
    ok = [t for t in iw.index if R[t].notna().all()]
    return te_min_weights(R[ok], rm, C.W_MIN, C.W_MAX)


def build_sleeve_overlay(w_rep, sleeve, size):
    """Sleeve as a self-financing overlay: +size x sleeve weights, -size x replica weights."""
    sl = pd.Series(sleeve, dtype=float); sl = sl / sl.sum()
    names = list(dict.fromkeys(list(w_rep.index) + list(sl.index))); a = pd.Series(0.0, index=names)
    a[sl.index] = size * sl; a[w_rep.index] = a[w_rep.index] - size * w_rep
    return a


def combine_weights(w_rep, overlay, e):
    names = list(dict.fromkeys(list(w_rep.index) + list(overlay.index))); w = pd.Series(0.0, index=names)
    w[w_rep.index] = e * w_rep; w[overlay.index] = w[overlay.index] + overlay
    neg = [t for t in w_rep.index if w[t] < 0]; w[neg] = 0.0
    return w


# ---- dual-benchmark simulation -------------------------------------------------
def simulate_bonus(e_grid, Y, rm, Rp_t, Rm_t, days_left, vol_ann, drift_ann, alpha_view, r_cash, te_scale=1.0,
                   n=None, seed=1, block=5):
    """P(bonus) = P(R_p(T) > max(0, R_sp(T))) for each equity exposure.
    Block bootstrap of historical days: the index and the book residual are drawn on the SAME days, so their
    joint behaviour in bad markets is kept; the index is rescaled to the implied volatility.
    Y: days x exposures array of the book's daily returns at each exposure; rm: index daily returns."""
    n = n or C.N_SIM; rng = np.random.default_rng(seed); d = max(int(days_left), 0); nh = len(rm); rows = []
    if d == 0:
        b = max(0.0, Rm_t)
        out = pd.DataFrame([dict(exposure=e, beta=np.nan, P_bonus=float(Rp_t > b), E_excess=Rp_t - b, q05=Rp_t - b, q95=Rp_t - b,
                                 E_return=Rp_t, r05=Rp_t, r95=Rp_t) for e in e_grid])
        out.attrs["P_market_up"] = float(Rm_t > 0); return out
    nb = math.ceil(d / block); st = rng.integers(0, nh - block + 1, size=(n, nb))
    idx = (st[:, :, None] + np.arange(block)[None, None, :]).reshape(n, nb * block)[:, :d]
    mz = (rm - rm.mean()) / sd(rm) * vol_ann / math.sqrt(252) + drift_ann / 252
    M = mz[idx]; RmT = (1 + Rm_t) * np.exp(np.log1p(M).sum(axis=1)) - 1; bench = np.maximum(0, RmT)
    for i, e in enumerate(e_grid):
        y = Y[:, i]; b = np.cov(y, rm)[0, 1] / np.var(rm, ddof=1); res = y - b * rm; res = (res - res.mean()) * te_scale
        D = b * M + res[idx] + alpha_view / d + (1 - e) * r_cash / 252
        RpT = (1 + Rp_t) * np.exp(np.log1p(D).sum(axis=1)) - 1; ex = RpT - bench
        rows.append(dict(exposure=e, beta=b, P_bonus=float(np.mean(ex > 0)), E_excess=float(ex.mean()), q05=float(np.quantile(ex, .05)),
                         q95=float(np.quantile(ex, .95)), E_return=float(RpT.mean()), r05=float(np.quantile(RpT, .05)), r95=float(np.quantile(RpT, .95))))
    out = pd.DataFrame(rows); out.attrs["P_market_up"] = float(np.mean(RmT > 0)); return out


# ---- helpers -------------------------------------------------------------------
def trading_days_between(a, b):
    if b <= a:
        return 0
    n = 0; d = a + timedelta(days=1)
    while d <= b:
        if d.weekday() < 5 and d not in C.HOLIDAYS:
            n += 1
        d += timedelta(days=1)
    return n


def current_phase(day):
    ph = C.PHASES[0]
    for p in C.PHASES:
        if p[0] <= day:
            ph = p
    return ph


def pct(x, d=2):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "n/a"
    t = f"{100 * x:.{d}f}%"
    return t[1:] if t.startswith("-") and float(t[1:-1]) == 0 else t      # no "-0.0%"


def money(x):
    return "n/a" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{round(x):,.0f}"


def status_word(use, warn):
    return "BREACH" if use > 1 else ("WARNING" if use > warn else "OK")
