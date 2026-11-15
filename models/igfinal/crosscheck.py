"""crosscheck.py - compare this Python version with the R version (../IGfinal) on the same frozen prices.
    python3 crosscheck.py [date]      default: the latest date present in both output folders
Deterministic results must agree; anything built on random draws (bootstrap intervals, the bonus
simulation) uses a different random-number generator in each language and is only compared loosely."""
import os, sys
import numpy as np
import pandas as pd

R_DIR = "../IGfinal/output"; PY_DIR = "output"
common = sorted(set(os.listdir(R_DIR)) & set(os.listdir(PY_DIR)) - {"validation"})
day = sys.argv[1] if len(sys.argv) > 1 else common[-1]
r = lambda f: pd.read_csv(os.path.join(R_DIR, day, f)); p = lambda f: pd.read_csv(os.path.join(PY_DIR, day, f))
rows = []
def cmp(name, a, b, tol):
    d = float(np.max(np.abs(np.asarray(a, float) - np.asarray(b, float)))); rows.append((name, d, tol, "PASS" if d <= tol else "FAIL"))
tr, tp = r("trades.csv").set_index("ticker"), p("trades.csv").set_index("ticker"); tp = tp.reindex(tr.index)
cmp("target weights, % (trades.csv)", tr.tgt_w, tp.tgt_w, 0.011)
cmp("target shares (trades.csv)", tr.tgt_shares, tp.tgt_shares, 1)
lr, lp = r("euler_shapley_legs.csv"), p("euler_shapley_legs.csv")
cmp("Euler by leg", lr.Euler, lp.Euler, 1e-8); cmp("Shapley by leg", lr.Shapley, lp.Shapley, 1e-8); cmp("stand-alone ES by leg", lr.iloc[:, 3], lp.iloc[:, 3], 1e-8)
er, ep = r("euler_positions.csv").set_index("position"), p("euler_positions.csv").set_index("position"); ep = ep.reindex(er.index)
cmp("Euler by position", er.active_ES, ep.active_ES, 1e-8)
cmp("Euler 90% interval, bootstrap (loose)", er[["lo", "hi"]].values, ep[["lo", "hi"]].values, 0.003)
sr, sp = r("stress.csv"), p("stress.csv")
cmp("stress: book return", sr.book, sp.book, 1e-8); cmp("stress: active return", sr.active, sp.active, 1e-8)
num = lambda s: float(str(s).replace("%", "").replace(",", ""))
kr, kp = r("risk.csv"), p("risk.csv"); keep = [i for i, m in enumerate(kr.Measure) if "interval" not in m]
cmp("risk table: absolute, % (as printed)", [num(kr.iloc[i, 2]) for i in keep], [num(kp.iloc[i, 2]) for i in keep], 0.011)
cmp("risk table: active, % (as printed)", [num(kr.iloc[i, 4]) for i in keep], [num(kp.iloc[i, 4]) for i in keep], 0.011)
out = pd.DataFrame(rows, columns=["Check", "Largest difference", "Tolerance", "Result"])
print(f"R vs Python on {day}\n" + out.to_string(index=False, float_format=lambda x: f"{x:.3g}"))
sys.exit(0 if (out.Result == "PASS").all() else 1)
