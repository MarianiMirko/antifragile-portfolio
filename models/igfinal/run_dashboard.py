"""run_dashboard.py - run daily or weekly, from the IGfinal_py folder.
    python3 run_dashboard.py           price source from config.py
    python3 run_dashboard.py live      today's prices (saves a snapshot)
    python3 run_dashboard.py frozen    rebuild from the latest (or configured) snapshot
Reads  input/holdings.csv (ticker,shares; shorts negative; one CASH row)
Writes output/<as-of date>/dashboard.html + CSV tables, output/nav_log.csv,
       output/transactions_log.csv, site_export/targets.json and rules.json"""
import json, math, os
from datetime import date
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import config as C
import lib as L
from lib import pct, money
from data import load_prices, pick_source
import html_kit as H

SRC = pick_source(); rng = np.random.default_rng(1); hh = math.sqrt(C.HORIZON)
for d_ in ("state", "site_export", "output"):
    os.makedirs(d_, exist_ok=True)

# ---- 1. holdings -------------------------------------------------------------
hf = "input/holdings.csv"; have_h = os.path.exists(hf)
Hd = pd.read_csv(hf, skipinitialspace=True) if have_h else pd.DataFrame({"ticker": ["CASH"], "shares": [C.INITIAL_CAPITAL]})
Hd["ticker"] = Hd["ticker"].astype(str).str.strip().str.upper().str.replace(".", "-", regex=False)      # BRK.B -> BRK-B (Yahoo)
cash = float(Hd.loc[Hd.ticker == "CASH", "shares"].sum())
pos = Hd[(Hd.ticker != "CASH") & (Hd.shares != 0)].groupby("ticker")["shares"].sum()

# ---- 2. data -----------------------------------------------------------------
rep_names = list(L.replica_names().index)
_lastf = "state/last_holdings.csv"                    # names held at the previous run: their prices value the trades in the log
_prev_names = [t for t in pd.read_csv(_lastf).ticker if t != "CASH"] if os.path.exists(_lastf) else []
universe = list(dict.fromkeys(rep_names + list(C.SLEEVE) + list(pos.index) + _prev_names))
P_full = load_prices(universe + [C.BENCH, C.VOL_INDEX], SRC); origin = P_full.attrs["origin"]
P = P_full.dropna(subset=universe + [C.BENCH])                 # common history of all names held
asof = P.index[-1].date(); px = P[universe].iloc[-1]; vix = float(P[C.VOL_INDEX].iloc[-1]) / 100; sp_now = float(P[C.BENCH].iloc[-1])
Rall = P[universe + [C.BENCH]].pct_change().iloc[1:]; nA = len(Rall)
if nA < C.RISK_WINDOW:
    raise SystemExit(f"Only {nA} days of common history: a held name is too recently listed.")
Rw = Rall.iloc[-C.RISK_WINDOW:]; rm = Rw[C.BENCH].values; Rrep = Rall.iloc[-min(C.REPLICA_LOOKBACK, nA):]

nw = cash + float((pos * px[pos.index]).sum()) if len(pos) else cash
if C.NET_WORTH_OVERRIDE is not None:
    nw = C.NET_WORTH_OVERRIDE
Rp_t = nw / C.INITIAL_CAPITAL - 1; Rm_t = sp_now / C.SP_START_LEVEL - 1; bench_t = max(0.0, Rm_t); excess_t = Rp_t - bench_t
days_left = L.trading_days_between(asof, C.GAME_END)
OUT = os.path.join("output", str(asof)); os.makedirs(OUT, exist_ok=True)

# ---- 3. exit rule and replica ---------------------------------------------------
# The sleeve is sold for good once the lead reaches EXIT_TRIGGER, or on the IPO date
exitf = "state/sleeve_exit.csv"; ex = pd.read_csv(exitf) if os.path.exists(exitf) else None
if C.EXIT_TRIGGER is not None and ex is None and have_h and excess_t >= C.EXIT_TRIGGER:      # None = no early exit (config.py)
    ex = pd.DataFrame({"date": [str(asof)], "reason": [f"lead of {pct(excess_t)} reached the exit trigger of {pct(C.EXIT_TRIGGER)}"]}); ex.to_csv(exitf, index=False)
exited = ex is not None and date.fromisoformat(str(ex["date"][0])) <= asof
_, ph_mult, ph_label = L.current_phase(max(asof, C.GAME_START))
if exited:
    ph_mult, ph_label = 0.0, f"Sleeve sold ({ex['reason'][0]}): replica only"
sleeve_on = C.SLEEVE_SIZE * ph_mult > 0; rep_method = C.REPLICA_CATCH_UP if sleeve_on else C.REPLICA_HOLD
w_rep = L.replica_weights(rep_method, Rrep, Rrep[C.BENCH].values)
_fx = pd.Series(getattr(C, "FIXED_WEIGHTS", {}) or {}, dtype=float)
if len(_fx):                                          # fixed holdings (portfolio manager): set weight, the replica fills the rest
    _rest = w_rep.drop([t for t in _fx.index if t in w_rep.index])
    w_rep = pd.concat([_rest * (1 - _fx.sum()) / _rest.sum(), _fx])
rep_d = Rw[w_rep.index].values @ w_rep.values; te_rep = L.sd(rep_d - rm) * math.sqrt(252); beta_rep = np.cov(rep_d, rm)[0, 1] / np.var(rm, ddof=1)

# ---- 4. speculative sleeve and active risk -------------------------------------------
a_full = L.build_sleeve_overlay(w_rep, C.SLEEVE, C.SLEEVE_SIZE * ph_mult)
book_ret = lambda w: Rw[w.index].values @ w.values
active_loss = lambda w: -(book_ret(w) - rm)
es_act = lambda s: L.ES_fhs(active_loss(L.combine_weights(w_rep, s * a_full, 1)))
budget = C.ACTIVE_ES_LIMIT if sleeve_on else C.REPLICA_ES_LIMIT      # monitoring limits: the sleeve is on or off, never scaled
es_full, es_zero, s = es_act(1), es_act(0), 1.0
a_s = s * a_full

# ---- 5. equity exposure: probability of the bonus --------------------------------
e_grid = np.round(np.arange(C.EXPOSURE_MIN, C.EXPOSURE_MAX + 1e-9, 0.05), 2)
Y = np.column_stack([book_ret(L.combine_weights(w_rep, a_s, e)) for e in e_grid])
L1 = active_loss(L.combine_weights(w_rep, a_s, 1)); te_scale = L.ewma_sigma(L1, C.LAMBDA)[-1] / L.sd(L1)
sim = lambda Rp0, Rm0: L.simulate_bonus(e_grid, Y, rm, Rp0, Rm0, days_left, vix * C.VIX_HAIRCUT, C.MARKET_DRIFT_ANN, C.ALPHA_VIEW, C.CASH_RATE_ANN, te_scale)
PB = sim(Rp_t, Rm_t)
best = PB[PB.P_bonus >= PB.P_bonus.max() - 0.005]; e_star = float(best.exposure[best.E_excess.idxmax()]); pb_star = PB[PB.exposure == e_star].iloc[0]
if getattr(C, "FULLY_INVESTED", False):              # plan rule: always fully invested; the table above stays as information
    e_star = float(e_grid.max()); pb_star = PB[PB.exposure == e_star].iloc[0]
rows = []
for nm, lvl in C.SP_START_ALTERNATIVES.items():
    r0 = sp_now / lvl - 1; x = sim(Rp_t, r0)
    rows.append({"S&P start level": f"{nm} ({lvl:.2f})", "S&P return so far": pct(r0), "Excess vs benchmark": pct(Rp_t - max(0, r0)),
                 "Best P(bonus)": pct(x.P_bonus.max(), 1), "at exposure": pct(x.exposure[x.P_bonus.idxmax()], 0)})
start_sens = pd.DataFrame(rows)

# ---- 6. target book and trades -----------------------------------------------------
w_tgt = L.combine_weights(w_rep, a_s, e_star); w_tgt = w_tgt[w_tgt.abs() > 1e-6]
tk = list(dict.fromkeys(list(w_tgt.index) + list(pos.index)))
cur_sh = pos.reindex(tk).fillna(0.0); tgt_w = w_tgt.reindex(tk).fillna(0.0)
tgt_sh = np.trunc(tgt_w * nw / px[tk]); w_cur = cur_sh * px[tk] / nw
_small = ((tgt_sh - cur_sh).abs() * px[tk]) < getattr(C, "MIN_ORDER_USD", 0)     # plan rule: orders too small to matter are not placed
tgt_sh = tgt_sh.where(~_small, cur_sh)
trades = pd.DataFrame({"ticker": [t.replace("-", ".") for t in tk], "price": px[tk].round(2).values, "cur_shares": cur_sh.values, "tgt_shares": tgt_sh.values,
                       "trade": (tgt_sh - cur_sh).values, "trade_usd": ((tgt_sh - cur_sh) * px[tk]).round().values, "cur_w": (100 * w_cur).round(2).values,
                       "tgt_w": (100 * tgt_w).round(2).values, "replica_w": (100 * w_rep.reindex(tk).fillna(0)).round(2).values})
def _action(r):
    if r.trade > 0: return "BUY TO COVER" if r.cur_shares < 0 else "BUY"
    if r.trade < 0: return "SELL SHORT" if (r.tgt_shares < 0 and r.cur_shares <= 0) else "SELL"
    return "-"
trades["action"] = trades.apply(_action, axis=1)
trades = trades.reindex(trades.tgt_w.abs().sort_values(ascending=False, kind="stable").index)
cash_after = nw - float((tgt_sh * px[tk]).sum()); turnover = float(trades.trade_usd.abs().sum()) / nw
trades.to_csv(os.path.join(OUT, "trades.csv"), index=False)

# ---- 6b. files for the team's website (antifragileportfolio.eu) ------------------------------
tg = {t.replace("-", "."): round(float(v), 5) for t, v in tgt_w.items() if abs(v) > 1e-6}; tg["CASH"] = round(max(0.0, 1 - float(tgt_w.sum())), 5)
_la = -book_ret(w_tgt); var95_1d = L.VaR_hist(_la * L.fhs_factors(_la), 0.95)
json.dump({"note": f"Target weights from IGfinal, prices of {asof}. Phase: {ph_label}. Fractions of the fund; CASH is the cash target.", "generated": str(asof), "targets": tg},
          open("site_export/targets.json", "w"), indent=2)
json.dump({"is_placeholder": False,
           "note": "Limits of the investment plan as monitored by IGfinal (config.py). Sector and stop-loss limits are proposals: the plan is an index replica plus a sleeve, so it has no stop-losses and its technology weight follows the index.",
           "limits": {"max_position_weight": C.LIMITS["max_name"], "max_sector_weight": 0.60, "min_cash_weight": 0, "max_cash_weight": round(1 - C.EXPOSURE_MIN, 4), "min_positions": 40,
                      "max_positions": C.LIMITS["max_tickers"], "stop_loss_pct": -0.30, "drift_threshold": 0.01, "max_var_95_1d": round(1.5 * var95_1d, 4), "allow_margin": False, "allow_short": False},
           "buy_criteria": [f"Replica: the {C.REPLICA_N} largest S&P 500 companies without {', '.join(C.REPLICA_EXCLUDE)}, at index weights while we are behind",
                            f"Sleeve: {pct(C.SLEEVE_SIZE, 0)} of the fund in {', '.join(C.SLEEVE)} until the IPO date ({C.IPO_DATE})",
                            "Every order comes from the IGfinal trade list and is recorded in the transaction log"],
           "sell_criteria": [(f"Exit: sell the whole sleeve once the fund is {pct(C.EXIT_TRIGGER, 1)} ahead of max(0, S&P 500), or on the IPO date" if C.EXIT_TRIGGER is not None
                              else "Exit: sell the whole sleeve on the IPO day, after the New York open. No early exit"),
                             "After the exit: hold the replica at minimum-tracking-error weights",
                             ("Always fully invested; orders smaller than " + money(getattr(C, "MIN_ORDER_USD", 0)) + " USD are not placed" if getattr(C, "FULLY_INVESTED", False) else
                              f"Cash rule: equity between {pct(C.EXPOSURE_MIN, 0)} and {pct(C.EXPOSURE_MAX, 0)}, set by the simulated probability of finishing above max(0, S&P 500)"),
                             "A breached limit on the dashboard is fixed before any other trade"]},
          open("site_export/rules.json", "w"), indent=2)

# ---- 7. risk ---------------------------------------------------------------------
def risk_block(w, label):
    w = w[w.abs() > 1e-8]
    if not len(w): return None
    La, Lr = -book_ret(w), active_loss(w); fa, fr = L.fit_t(La), L.fit_t(Lr)
    def ci(x):
        xs = x * L.fhs_factors(x); n = len(xs)
        return hh * np.quantile([L.ES_hist(xs[L.block_index(n, rng)], C.CONF) for _ in range(C.N_BOOT)], [.05, .95])
    ca, cr = ci(La), ci(Lr)
    def col(x, f, c, usd=False):
        v = [L.ES_fhs(x), None, hh * L.ES_hist(x, C.CONF), hh * L.ES_normal(x, C.CONF), hh * L.ES_t(f["s"], f["nu"], C.CONF), hh * L.ES_t4_reference(x, C.CONF),
             hh * L.VaR_hist(x, C.CONF), hh * L.expectile(x, C.CONF)]
        fmt = (lambda z: money(z * nw)) if usd else pct
        return [f"{fmt(c[0])} to {fmt(c[1])}" if z is None else fmt(z) for z in v]
    return pd.DataFrame({"Book": label, "Measure": ["ES conditional (decision measure)", "  90% interval", "ES historical, unconditional", "ES normal",
                         f"ES Student-t, fitted (nu {fa['nu']:.1f} / {fr['nu']:.1f})", "ES t(4), as in the reference code", "VaR historical", "Expectile"],
                         "Absolute": col(La, fa, ca), "Absolute, USD": col(La, fa, ca, True), "Active vs S&P": col(Lr, fr, cr)})
w_cur_nz = w_cur[w_cur.abs() > 1e-8]
RISK = pd.concat([x for x in (risk_block(w_tgt, "Target"), risk_block(w_cur_nz, "Current")) if x is not None], ignore_index=True)
RISK.to_csv(os.path.join(OUT, "risk.csv"), index=False)
es_tgt_active = L.ES_fhs(active_loss(w_tgt)); es_cur_active = L.ES_fhs(active_loss(w_cur_nz)) if len(w_cur_nz) else L.ES_fhs(rm)   # all cash: active loss = S&P return

# Euler by position on the ACTIVE loss (the S&P enters as a short leg), with bootstrap intervals
Xp = np.column_stack([-Rw[w_tgt.index].values * w_tgt.values, rm]); pnames = list(w_tgt.index) + ["SP500"]
kf = L.fhs_factors(Xp.sum(axis=1)); Xs = Xp * kf[:, None]
euler = lambda X: hh * (X * L.es_weights(X.sum(axis=1), C.CONF)[:, None]).sum(axis=0)
eul = euler(Xs); bt = np.array([euler(Xs[L.block_index(len(Xs), rng)]) for _ in range(C.N_BOOT)])
EUL = pd.DataFrame({"position": pnames, "weight": list(w_tgt.values) + [-1.0], "active_ES": eul, "lo": np.quantile(bt, .05, axis=0), "hi": np.quantile(bt, .95, axis=0), "share": eul / eul.sum()})
EUL = EUL.reindex(EUL.active_ES.abs().sort_values(ascending=False, kind="stable").index).reset_index(drop=True)
EUL.to_csv(os.path.join(OUT, "euler_positions.csv"), index=False)

# Euler vs exact Shapley by leg of the strategy
sz = C.SLEEVE_SIZE * ph_mult * s; slw = pd.Series(C.SLEEVE, dtype=float); slw = sz * slw / slw.sum()
legs = {"Replica tracking error": -(rep_d - rm), "Cash (under-investment)": (1 - e_star) * rep_d}
for th in dict.fromkeys(C.THEMES[t] for t in slw.index):
    nm = [t for t in slw.index if C.THEMES[t] == th]; legs["Sleeve: " + th] = -(Rw[nm].values @ slw[nm].values)
legs["Sleeve funding (less replica)"] = sz * rep_d
legs["Other (rounding)"] = active_loss(w_tgt) - sum(legs.values())
legs = {k: v for k, v in legs.items() if np.abs(v).max() > 1e-9}
LGs = np.column_stack(list(legs.values())) * kf[:, None]; rho = lambda x: hh * L.ES_hist(x, C.CONF)
LEGS = pd.DataFrame({"leg": list(legs), "Euler": euler(LGs), "Shapley": L.shapley_exact(LGs, rho), "Stand-alone": [rho(LGs[:, j]) for j in range(LGs.shape[1])]})
LEGS.to_csv(os.path.join(OUT, "euler_shapley_legs.csv"), index=False)

# ---- 8. constraints ------------------------------------------------------------------
def check(w, es_a, label):
    w = w[w.abs() > 1e-8]; expo = float(w.sum()); mx = float(w.abs().max()) if len(w) else 0.0; gs = float(w[w < 0].abs().sum()); nt = len(w)
    st = lambda v, lim: L.status_word(v / lim, C.LIMITS["warn"])
    return pd.DataFrame({"Book": label, "Constraint": ["Net equity exposure", "Largest single position", "Number of tickers", "Gross short", "Cash", "Active ES (5-day, 97.5%)"],
        "Value": [pct(expo, 1), pct(mx, 1), nt, pct(gs, 1), pct(1 - expo, 1), pct(es_a)],
        "Limit": [f"{pct(C.EXPOSURE_MIN, 0)} to {pct(C.EXPOSURE_MAX, 0)}", pct(C.LIMITS["max_name"], 0), C.LIMITS["max_tickers"], pct(C.LIMITS["max_gross_short"], 0), f">= {pct(C.LIMITS['min_cash'], 0)}", pct(budget)],
        "Status": ["BREACH" if (expo < C.EXPOSURE_MIN - 1e-9 or expo > C.EXPOSURE_MAX + .005) else "OK", st(mx, C.LIMITS["max_name"]), st(nt, C.LIMITS["max_tickers"]),
                   (st(gs, C.LIMITS["max_gross_short"]) if C.LIMITS["max_gross_short"] > 0 else ("BREACH" if gs > 1e-9 else "OK")),
                   "BREACH" if 1 - expo < C.LIMITS["min_cash"] - .005 else "OK", st(es_a, budget)]})
LIM = pd.concat([check(w_cur_nz, es_cur_active, "Current"), check(w_tgt, es_tgt_active, "Target")], ignore_index=True)
LIM.to_csv(os.path.join(OUT, "constraints.csv"), index=False)

# ---- 9. stress tests --------------------------------------------------------------------
def stress_one(shock, name, typ):
    """shock: Series of returns indexed by ticker (incl. the index). A name without data moves with the index."""
    m = shock.get(C.BENCH, np.nan)
    if pd.isna(m): return None
    sh = shock.reindex(w_tgt.index).fillna(m); rp = float((w_tgt * sh).sum())
    return dict(Scenario=name, Type=typ, sp=float(m), book=rp, active=rp - m, dual=rp - max(0.0, m))
episodes = [("Q4 2018 sell-off (3 Oct - 24 Dec 2018)", "2018-10-03", "2018-12-24"), ("COVID crash (19 Feb - 23 Mar 2020)", "2020-02-19", "2020-03-23"),
            ("2022 bear market (3 Jan - 14 Oct 2022)", "2022-01-03", "2022-10-14"), ("Volatility spike (1 - 5 Aug 2024)", "2024-08-01", "2024-08-05"),
            ("Tariff shock (2 - 8 Apr 2025)", "2025-04-02", "2025-04-08")]
ST = []
for name, a, b in episodes:
    a_, b_ = pd.Timestamp(a), pd.Timestamp(b); seg = P_full.loc[a_ - pd.Timedelta(days=1):b_]
    if len(seg) < 2 or P_full.index[0] > a_: continue
    ST.append(stress_one(seg.iloc[-1] / seg.iloc[0] - 1, name, "Historical replay"))
act_d = -active_loss(w_tgt); dates_w = Rw.index
for k in (1, 5):
    cs = pd.Series(act_d).rolling(k).sum(); j = int(cs.idxmin()); rws = Rw.iloc[j - k + 1:j + 1]
    ST.append(stress_one((1 + rws).prod() - 1, f"Worst {k}-day active loss in the last {C.RISK_WINDOW} days (to {dates_w[j].date()})", "Historical worst"))
if os.path.exists("input/stress_scenarios.csv"):
    sc = pd.read_csv("input/stress_scenarios.csv")
    for nm in dict.fromkeys(sc.scenario):
        d = sc[sc.scenario == nm].set_index("ticker")["shock"]; other = d["OTHER"] if "OTHER" in d.index else d[C.BENCH]
        ST.append(stress_one(pd.Series({t: d.get(t, other) for t in list(w_tgt.index) + [C.BENCH]}), nm, "Hypothetical"))
ST = pd.DataFrame([x for x in ST if x]); ST.to_csv(os.path.join(OUT, "stress.csv"), index=False)

# ---- 10. transaction trail, NAV log, buy-and-hold ----------------------------------------
snap = pd.DataFrame({"ticker": list(pos.index) + ["CASH"], "shares": list(pos.values) + [cash]}); lastf, initf, trf = "state/last_holdings.csv", "state/initial_holdings.csv", "output/transactions_log.csv"
if have_h:
    prev = pd.read_csv(lastf) if os.path.exists(lastf) else pd.DataFrame({"ticker": ["CASH"], "shares": [C.INITIAL_CAPITAL]})
    b = prev[prev.ticker != "CASH"].set_index("ticker")["shares"]; a = snap[snap.ticker != "CASH"].set_index("ticker")["shares"]
    allt = list(dict.fromkeys(list(b.index) + list(a.index))); b = b.reindex(allt).fillna(0.0); a = a.reindex(allt).fillna(0.0); ch = [t for t in allt if abs(a[t] - b[t]) > 1e-9]
    if ch:
        pxx = P[ch].iloc[-1]
        new = pd.DataFrame({"recorded": str(asof), "ticker": ch, "shares_before": b[ch].values, "shares_after": a[ch].values, "trade": (a[ch] - b[ch]).values,
                            "ref_close": pxx.round(2).values, "value_usd": ((a[ch] - b[ch]) * pxx).round().values, "phase": ph_label})
        old = pd.read_csv(trf) if os.path.exists(trf) else None
        (new if old is None else pd.concat([old, new], ignore_index=True)).to_csv(trf, index=False)
    snap.to_csv(lastf, index=False)
    if not os.path.exists(initf) and len(pos):
        snap.assign(date=str(asof)).to_csv(initf, index=False)
logf = "output/nav_log.csv"
row = pd.DataFrame([dict(date=str(asof), net_worth=round(nw), sp500=round(sp_now, 2), R_p=round(Rp_t, 5), R_sp=round(Rm_t, 5), bench=round(bench_t, 5), excess=round(excess_t, 5),
                         exposure=round(float(w_cur_nz.sum()), 4), active_ES=round(es_cur_active, 5), P_bonus=round(float(pb_star.P_bonus), 4), source=SRC)])
LOG = pd.read_csv(logf) if os.path.exists(logf) else row.iloc[0:0]
if have_h:                                           # nothing is logged on the all-cash assumption
    LOG = pd.concat([LOG[LOG.date != str(asof)], row], ignore_index=True).sort_values("date"); LOG.to_csv(logf, index=False)
BH = None
if os.path.exists(initf):
    ih = pd.read_csv(initf); ip = ih[ih.ticker != "CASH"]
    if all(t in P.columns for t in ip.ticker):
        seg = P.loc[pd.Timestamp(ih.date[0]):, list(ip.ticker)]
        BH = pd.DataFrame({"date": seg.index, "r": (float(ih.loc[ih.ticker == "CASH", "shares"].sum()) + seg.values @ ip.shares.values) / C.INITIAL_CAPITAL - 1})

# ---- 11. figures ---------------------------------------------------------------------------
INK, INK2, BLUE, ORANGE, GREY, GREEN = "#0b0b0b", "#52514e", "#2a78d6", "#eb6834", "#b0afa8", "#1baf7a"
plt.rcParams.update({"font.size": 9, "axes.spines.top": False, "axes.spines.right": False, "axes.edgecolor": "#c9c8c0", "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
                     "axes.grid": True, "grid.color": "#e6e5e0", "grid.linewidth": .5, "axes.axisbelow": True, "axes.titleweight": "bold", "axes.titlesize": 10.5, "axes.titlelocation": "left"})
def save(fig, f):
    for ax_ in fig.axes:                              # long titles: anchor them to the figure, not the axes
        t_ = ax_.get_title(loc="left") or ax_.get_title(); ax_.set_title(""); fig.suptitle(t_, x=0.01, ha="left", fontsize=10.5, fontweight="bold")
    fig.tight_layout(); fig.savefig(os.path.join(OUT, f), dpi=160, facecolor="white"); plt.close(fig)
fig, ax = plt.subplots(figsize=(7, 3.6)); ax.plot(100 * PB.exposure, 100 * PB.P_bonus, color=BLUE, lw=1.8, marker="o", ms=4)
ax.axvline(100 * e_star, color=INK, ls="--", lw=1); ax.annotate(f"chosen: {100 * e_star:.0f}%", (100 * e_star, 100 * PB.P_bonus.max()), textcoords="offset points", xytext=(-6 if e_star > .7 else 6, 8), ha="right" if e_star > .7 else "left", color=INK)
ax.margins(y=.2); ax.set(title="Probability of beating max(0, S&P 500) at game end, by equity exposure", xlabel="Equity exposure, % of net worth (rest in cash)", ylabel="P(bonus), %"); save(fig, "fig_pbonus.png")
fig, ax = plt.subplots(figsize=(7, 3)); y = np.arange(len(LEGS))[::-1]
ax.barh(y + .18, 100 * LEGS.Euler, height=.34, color=BLUE, label="Euler"); ax.barh(y - .18, 100 * LEGS.Shapley, height=.34, color=ORANGE, label="Shapley"); ax.axvline(0, color=INK2, lw=.6)
ax.set_yticks(y); ax.set_yticklabels(LEGS.leg); ax.legend(frameon=False, ncol=2, loc="lower right"); ax.set(title="Who uses the active-risk budget: contribution to 5-day active ES", xlabel="% of net worth"); save(fig, "fig_legs.png")
top = EUL.head(14).iloc[::-1]; fig, ax = plt.subplots(figsize=(7, 4.2)); yy = np.arange(len(top))
ax.hlines(yy, 100 * top.lo, 100 * top.hi, color=BLUE, alpha=.45, lw=5); ax.plot(100 * top.active_ES, yy, "o", color=BLUE, ms=5); ax.axvline(0, color=INK2, lw=.6)
ax.set_yticks(yy); ax.set_yticklabels(top.position); ax.set(title="Euler contribution to active ES by position, with 90% interval", xlabel="% of net worth (left of zero = reduces active risk)"); save(fig, "fig_euler_positions.png")
ds = ST.sort_values("active"); fig, ax = plt.subplots(figsize=(7, 3.8)); yy = np.arange(len(ds)); ax.barh(yy, 100 * ds.active, color=BLUE, height=.65); ax.axvline(0, color=INK2, lw=.6)
for yv, v in zip(yy, ds.active):
    ax.annotate(f"{100 * v:+.1f}%", (100 * v, yv), textcoords="offset points", xytext=(-4 if v < 0 else 4, 0), ha="right" if v < 0 else "left", va="center", color=INK, fontsize=8)
ax.margins(x=.2); ax.set_yticks(yy); ax.set_yticklabels(ds.Scenario, fontsize=7.5); ax.set(title="Stress tests: target book minus S&P 500", xlabel="Active return, % of net worth"); save(fig, "fig_stress.png")
seg = P.loc[pd.Timestamp("2026-11-06"):, C.BENCH]; fig, ax = plt.subplots(figsize=(7, 3.6)); ax.axhline(0, color=INK2, lw=.6)
ax.plot(seg.index, 100 * (seg / C.SP_START_LEVEL - 1), color=GREY, lw=1.6, label="S&P 500"); ax.plot(seg.index, 100 * np.maximum(0, seg / C.SP_START_LEVEL - 1), color=ORANGE, lw=1.6, ls="--", label="Benchmark max(0, S&P)")
if BH is not None: ax.plot(BH.date, 100 * BH.r, color=GREEN, lw=1.6, label="Buy-and-hold of first portfolio")
ax.plot([pd.Timestamp("2026-11-06")] + list(pd.to_datetime(LOG.date)), [0] + list(100 * LOG.R_p), color=BLUE, lw=1.8, marker="o", ms=4, label="Portfolio")
ax.legend(frameon=False, ncol=2, fontsize=8); fig.autofmt_xdate(); ax.set(title="Return since the start of the game", ylabel="%"); save(fig, "fig_performance.png")

# ---- 12. dashboard ---------------------------------------------------------------------------
ntr = int((trades.trade != 0).sum()); cur_st = LIM[LIM.Book == "Current"].Status; worst_lim = "BREACH" if (cur_st == "BREACH").any() else ("WARNING" if (cur_st == "WARNING").any() else "OK")
PBf = pd.DataFrame({"Exposure": [pct(x, 0) for x in PB.exposure], "Beta": [f"{x:.2f}" for x in PB.beta], "P(bonus)": [pct(x, 1) for x in PB.P_bonus], "Expected excess": [pct(x) for x in PB.E_excess],
                    "Excess, 5% to 95%": [f"{pct(a, 1)} to {pct(b, 1)}" for a, b in zip(PB.q05, PB.q95)], "Expected final return": [pct(x) for x in PB.E_return],
                    "Final return, 5% to 95%": [f"{pct(a, 1)} to {pct(b, 1)}" for a, b in zip(PB.r05, PB.r95)]})
e14 = EUL.head(14)
EULf = pd.DataFrame({"Position": [p.replace("-", ".") for p in e14.position], "Weight": [pct(x, 1) for x in e14.weight], "Active ES contribution": [pct(x, 3) for x in e14.active_ES],
                     "90% interval": [f"{pct(a, 3)} to {pct(b, 3)}" for a, b in zip(e14.lo, e14.hi)], "Share of active ES": [pct(x, 1) for x in e14.share]})
LEGf = pd.DataFrame({"Leg": LEGS.leg, "Euler": [pct(x, 3) for x in LEGS.Euler], "Euler share": [pct(x, 1) for x in LEGS.Euler / LEGS.Euler.sum()], "Shapley": [pct(x, 3) for x in LEGS.Shapley],
                     "Shapley share": [pct(x, 1) for x in LEGS.Shapley / LEGS.Shapley.sum()], "Stand-alone ES": [pct(x, 3) for x in LEGS["Stand-alone"]]})
STf = pd.DataFrame({"Scenario": ST.Scenario, "Type": ST.Type, "S&P 500": [pct(x, 1) for x in ST.sp], "Target book": [pct(x, 1) for x in ST.book], "Book minus S&P": [pct(x, 1) for x in ST.active],
                    "Book minus max(0, S&P)": [pct(x, 1) for x in ST.dual]})
TRf = trades[(trades.trade != 0) | (trades.tgt_shares != 0)].copy(); TRf["price"] = TRf.price.map("{:.2f}".format); TRf["trade_usd"] = TRf.trade_usd.map(money)
for c_ in ("cur_shares", "tgt_shares", "trade"): TRf[c_] = TRf[c_].map("{:.0f}".format)
trail = pd.read_csv(trf) if os.path.exists(trf) else None
body = "".join([
    "<h1>Investment Game dashboard</h1>",
    f'<p class="meta">Data as of {asof} &middot; {days_left} trading days left (last close {C.GAME_END}) &middot; {H.esc(origin)}</p>',
    "" if have_h else '<p class="BREACH">No input/holdings.csv found: the book is assumed to be 100% cash since the start. Copy your MarketWatch positions into input/holdings.csv to get real numbers.</p>',
    '<div class="tiles">', H.tile("Net worth", money(nw), f"return {pct(Rp_t)}"), H.tile("Benchmark max(0, S&P)", pct(bench_t), f"S&P 500 {pct(Rm_t)} from {C.SP_START_LEVEL}"),
    H.tile("Excess over benchmark", pct(excess_t), "currently qualifies for the bonus" if excess_t > 0 else "currently below the benchmark"),
    H.tile("P(bonus) at game end", pct(pb_star.P_bonus, 0), f"at {100 * e_star:.0f}% equity; S&P ends up in {pct(PB.attrs['P_market_up'], 0)} of paths"),
    H.tile("Constraints (current book)", f'<span class="{worst_lim}">{worst_lim}</span>', "see section 1"), "</div>",
    "<h2>What the rules say today</h2><ul>",
    f"<li>Phase: {H.esc(ph_label)}. Sleeve target {pct(C.SLEEVE_SIZE * ph_mult * s, 0)} of the portfolio ({', '.join(C.SLEEVE)}), replica {pct(1 - C.SLEEVE_SIZE * ph_mult * s, 0)}.</li>",
    (f'<li class="WARNING">{" and ".join(C.NOT_IN_SP500)} are US-listed but not S&amp;P 500 constituents. The case says the universe is the constituents: confirm they are allowed.</li>' if sleeve_on and C.NOT_IN_SP500 else ""),
    (("<li>Fixed holdings set by the portfolio manager: " + ", ".join(t + " " + pct(v, 0) for t, v in C.FIXED_WEIGHTS.items())
      + "; the replica fills the rest.</li>") if getattr(C, "FIXED_WEIGHTS", None) else "") +
    f"<li>Replica: {len(w_rep)} largest S&amp;P 500 companies without {', '.join(C.REPLICA_EXCLUDE)}, " + ("at index weights (catch-up phase: beta close to 1)" if rep_method == "index" else "at minimum-tracking-error weights (holding phase: smallest drift from the index)")
    + f". Beta over the window {beta_rep:.2f}, tracking error {pct(te_rep, 1)} a year.</li>",
    (f"<li>Exit rule: the sleeve is sold once the lead over the benchmark reaches {pct(C.EXIT_TRIGGER, 1)} or on the IPO date. Today the excess is {pct(excess_t)}" if C.EXIT_TRIGGER is not None
     else f"<li>Exit rule: the sleeve is sold on the IPO day, after the New York open; there is no early exit. Today the excess is {pct(excess_t)}")
    + (": <b>exit already made</b>" if exited else (" (no holdings recorded)" if not have_h else ": not reached")) + f". Active ES with the sleeve {pct(es_full)}, replica alone {pct(es_zero)}, monitoring limit {pct(budget)}.</li>",
    (f"<li>Equity exposure: <b>{pct(e_star, 0)}</b>, always fully invested (plan rule). Section 2 shows what the simulation says for lower exposures.</li>" if getattr(C, "FULLY_INVESTED", False) else
     f"<li>Equity exposure with the highest bonus probability inside the {pct(C.EXPOSURE_MIN, 0)}-{pct(C.EXPOSURE_MAX, 0)} band: <b>{pct(e_star, 0)}</b>.</li>"),
    f"<li>{ntr} orders to reach the target, turnover {pct(turnover, 0)} of net worth, cash after trades about {money(cash_after)}.</li></ul>",
    "<h2>1. Investment-plan constraints</h2>", H.table(LIM, status=True),
    '<p class="note">Limits are set in config.py (LIMITS, exposure band, active-ES limits). The case says constraints are assessed daily, so run this every day the book changes.</p>',
    '<h2>2. Bonus probability and equity exposure</h2><img src="fig_pbonus.png" alt="Bonus probability by equity exposure">', H.table(PBf),
    f'<p class="note">{C.N_SIM:,} paths to the last close. Each path strings together 5-day blocks of real past days, so the book and the index move together as they did historically. '
    f"Market volatility is set to VIX x {C.VIX_HAIRCUT} = {pct(vix * C.VIX_HAIRCUT, 1)} a year, drift {pct(C.MARKET_DRIFT_ANN, 0)} a year, alpha view {pct(C.ALPHA_VIEW, 1)}.</p>",
    "<p>The starting S&amp;P level is still to be confirmed. It changes the picture this much:</p>", H.table(start_sens),
    "<h2>3. Trade list</h2>", H.table(TRf), '<p class="note">MarketWatch symbols, whole shares, market orders. Prices are the last close.</p>',
    f"<h2>4. Risk ({C.HORIZON}-day horizon, {100 * C.CONF}%)</h2>", H.table(RISK),
    f'<p class="note">The decision measure restates the last {C.RISK_WINDOW} days at today\'s volatility (filtered historical simulation), the model that passed the backtest in validate.py. The t(4) row is the measure of the reference code, shown for comparison.</p>',
    '<h2>5. Where the active risk comes from</h2><img src="fig_legs.png" alt="Active ES by strategy leg, Euler and Shapley">', H.table(LEGf),
    f'<p class="note">Legs add up to the book minus the S&amp;P. Euler is the marginal contribution. Shapley is the exact value of the game v(S) = ES of the legs in S, over all {2 ** LGs.shape[1]} coalitions.</p>',
    '<img src="fig_euler_positions.png" alt="Euler contribution by position">', H.table(EULf),
    '<h2>6. Stress tests</h2><img src="fig_stress.png" alt="Active return in stress scenarios">', H.table(STf),
    '<p class="note">Historical replays hold today\'s target weights through the episode. In episodes before a held name was listed (PLTR 2020, GEV 2024) that name is assumed to move with the index. Hypothetical shocks come from input/stress_scenarios.csv; names not listed there move with the "OTHER" row.</p>',
    '<h2>7. Performance and trail</h2><img src="fig_performance.png" alt="Return since the start of the game">',
    (f"<p>Buy-and-hold of the first recorded portfolio: {pct(BH.r.iloc[-1])}; actual portfolio: {pct(Rp_t)}; difference from trading: {pct(Rp_t - BH.r.iloc[-1])}.</p>" if BH is not None
     else '<p class="note">The buy-and-hold comparison starts once a first portfolio has been recorded in input/holdings.csv.</p>'),
    ("<p>Transaction trail (last 15 rows of output/transactions_log.csv):</p>" + H.table(trail.tail(15)) if trail is not None and len(trail) else ""),
    "<h2>Limitations</h2><ul><li>Prices are Yahoo closes without dividends; MarketWatch fills at its own quotes, and net worth there is the reference. Use NET_WORTH_OVERRIDE if they differ.</li>",
    "<li>The transaction trail is built from changes in holdings between runs and priced at the close of the run date, not at the execution price.</li>",
    "<li>The index weights are those of 12 Nov 2026 and drift with prices. The sleeve is a view on one event and has no history to test.</li></ul>"])
open(os.path.join(OUT, "dashboard.html"), "w").write(H.page(f"Investment Game {asof}", body))

# ---- console summary ---------------------------------------------------------------------------
pd.set_option("display.width", 220); pd.set_option("display.max_columns", 20); pd.set_option("display.max_rows", 100)
ln = lambda: print("-" * 110)
ln(); print(f" INVESTMENT GAME | as of {asof} | {days_left} trading days left | {origin}"); ln()
print(f" Net worth {money(nw)} | return {pct(Rp_t)} | S&P {pct(Rm_t)} | benchmark {pct(bench_t)} | excess {pct(excess_t)} | VIX {pct(vix, 1)}")
print(f" Replica: {len(w_rep)} names, {rep_method} weights, TE {pct(te_rep)}/yr, beta {beta_rep:.2f} | {ph_label} | exit trigger {'none' if C.EXIT_TRIGGER is None else pct(C.EXIT_TRIGGER, 1)} | "
      f"active ES with sleeve {pct(es_full)}, replica {pct(es_zero)}, limit {pct(budget)} | sleeve {pct(C.SLEEVE_SIZE * ph_mult * s, 0)} of portfolio")
print(f" Exposure e* = {e_star:.2f} | P(bonus) {pct(pb_star.P_bonus, 1)} | P(S&P ends up) {pct(PB.attrs['P_market_up'], 1)} | {ntr} orders, turnover {pct(turnover, 0)}"); ln()
for t_ in (PBf, start_sens, LIM, RISK, LEGf, EULf.head(10), STf):
    print(t_.to_string(index=False)); ln()
print(" Dashboard:", os.path.join(OUT, "dashboard.html"))
