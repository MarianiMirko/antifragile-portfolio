"""Run the team's allocation model (models/igfinal, written by Lorenzo) and hand its results to the site.

The model itself is not changed: this script feeds it the positions read from MarketWatch,
runs models/igfinal/run_dashboard.py exactly as its author runs it, and copies what it produces:

    content/targets.json     the model's target weights (drives "Target weights and rebalancing")
    data/igfinal.json        standing against max(0, S&P 500), bonus probability, constraints,
                             trade list, risk, stress tests (shown on the Risk page)
    data/igfinal/            the model's own dashboard and figures

Usage
    python scripts/run_igfinal.py            live prices from Yahoo (what the GitHub workflow runs)
    python scripts/run_igfinal.py frozen     prices from models/igfinal/data/snapshots/, for testing

The model values the fund at the last completed session. If a trade was made after that close,
positions and prices would not belong to the same moment, and the model's permanent exit rule
could fire on a number that is not real. In that case the model is not run: the previous results
stay, with a note, until the session of the trade has closed.

A failure here never stops the site update: the previous results are kept and the error is shown.
"""
import contextlib
import io
import json
import os
import runpy
import shutil
import sys
import time as time_module
import traceback
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "models" / "igfinal"
OUT_JSON = ROOT / "data" / "igfinal.json"
OUT_DIR = ROOT / "data" / "igfinal"
TARGETS = ROOT / "content" / "targets.json"
NY = ZoneInfo("America/New_York")


def load(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(obj, indent=1, ensure_ascii=False, allow_nan=False) + "\n"
    if not path.exists() or path.read_text(encoding="utf-8") != text:
        path.write_text(text, encoding="utf-8")


def num(x):
    """A plain float, or None for missing values (JSON has no NaN)."""
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return x if x == x and abs(x) != float("inf") else None


def table(df):
    return {"columns": [str(c) for c in df.columns],
            "rows": [[(v if isinstance(v, str) else (int(v) if float(v).is_integer() else num(v))) if v is not None else None
                      for v in row] for row in df.itertuples(index=False)]}


def price_date(now, holidays):
    """The last session the model will see: today's only after 17:00 in New York (see models/igfinal/data.py)."""
    ny = now.astimezone(NY)
    d = ny.date() if ny.hour >= 17 else ny.date() - timedelta(days=1)
    while d.weekday() >= 5 or d in holidays:
        d -= timedelta(days=1)
    return d


def trades_after(day):
    """Executed orders later than the close of `day` (dates without a zone are New York time)."""
    close = datetime.combine(day, time(16, 0), tzinfo=NY)
    late = []
    for t in (load(ROOT / "data" / "transactions.json", {}) or {}).get("transactions", []):
        ts = datetime.fromisoformat(str(t["date"]))
        ts = ts.replace(tzinfo=NY) if ts.tzinfo is None else ts
        if ts > close:
            late.append(t)
    return late


def write_holdings():
    """data/holdings.json (MarketWatch) -> models/igfinal/input/holdings.csv (ticker,shares; one CASH row)."""
    h = load(ROOT / "data" / "holdings.json", {}) or {}
    cfg = load(ROOT / "config" / "fund.json", {}) or {}
    cash = h.get("cash")
    if cash is None:
        cash = cfg.get("initial_capital", 0)
    cash = float(cash) - float(h.get("cash_borrowed") or 0)
    lines = ["ticker,shares"] + [f"{p['ticker']},{float(p['shares']):g}" for p in h.get("positions", []) if float(p.get("shares") or 0)]
    lines.append(f"CASH,{cash:.2f}")
    (MODEL / "input" / "holdings.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return h


def keep_previous(status, message, now):
    prev = load(OUT_JSON, {}) or {}
    prev.update({"status": status, "message": message, "checked_at": now.isoformat(timespec="seconds")})
    save(OUT_JSON, prev)
    print(f"allocation model: {status}: {message}")


def main():
    mode = "frozen" if "frozen" in sys.argv[1:] else "live"
    now = datetime.now(timezone.utc)
    sys.path.insert(0, str(MODEL))
    os.chdir(MODEL)
    import config as C                                    # the model's own settings

    day = price_date(now, set(C.HOLIDAYS))
    late = trades_after(day) if mode == "live" else []
    if late:
        keep_previous("waiting", f"{len(late)} trade(s) were made after the close of {day}, the last session the model "
                      "can price. It runs again once the session of the trade has closed.", now)
        return

    holdings = write_holdings()
    log = io.StringIO()
    try:
        old_argv = sys.argv
        sys.argv = ["run_dashboard.py", mode]
        for attempt in range(1, 5):
            try:
                with contextlib.redirect_stdout(log):
                    g = runpy.run_path(str(MODEL / "run_dashboard.py"), run_name="__main__")
                break
            except SystemExit as exc:
                # Yahoo sometimes fails on one ticker of a large parallel download (on a fresh machine its
                # time-zone cache is locked by the other threads). The model stops before writing anything,
                # so it is safe to run it again.
                if "Download failed" not in str(exc) or attempt == 4:
                    raise
                print(f"allocation model: attempt {attempt} stopped ({exc}); trying again")
                time_module.sleep(6)
    except BaseException as exc:                          # SystemExit included: the model stops that way when a download fails
        if isinstance(exc, KeyboardInterrupt):
            raise
        traceback.print_exc()
        keep_previous("error", f"The model did not complete its last run ({type(exc).__name__}: {exc}). "
                      "The figures below are from its previous run.", now)
        return
    finally:
        sys.argv = old_argv

    C, PB, pb = g["C"], g["PB"], g["pb_star"]
    asof = g["asof"]
    targets = load(MODEL / "site_export" / "targets.json", {}) or {}
    ex = g["ex"]
    result = {
        "status": "ok", "message": None,
        "generated_at": now.isoformat(timespec="seconds"), "checked_at": now.isoformat(timespec="seconds"),
        "asof": str(asof), "origin": g["origin"], "days_left": int(g["days_left"]),
        "holdings_as_of": holdings.get("as_of"), "has_positions": bool(len(g["pos"])),
        "standing": {"net_worth": num(g["nw"]), "fund_return": num(g["Rp_t"]), "sp_return": num(g["Rm_t"]),
                     "benchmark": num(g["bench_t"]), "excess": num(g["excess_t"]), "sp_level": num(g["sp_now"]),
                     "sp_start_level": num(C.SP_START_LEVEL), "vix": num(g["vix"])},
        "phase": {"label": g["ph_label"], "sleeve_on": bool(g["sleeve_on"]), "exited": bool(g["exited"]),
                  "exit_date": str(ex["date"][0]) if ex is not None else None,
                  "exit_reason": str(ex["reason"][0]) if ex is not None else None,
                  "exit_trigger": num(C.EXIT_TRIGGER), "ipo_date": str(C.IPO_DATE),
                  "sleeve_size": num(C.SLEEVE_SIZE), "sleeve": list(C.SLEEVE), "not_in_sp500": list(C.NOT_IN_SP500)},
        "replica": {"method": g["rep_method"], "names": int(len(g["w_rep"])), "excluded": list(C.REPLICA_EXCLUDE),
                    "beta": num(g["beta_rep"]), "tracking_error": num(g["te_rep"])},
        "exposure": {"chosen": num(g["e_star"]), "min": num(C.EXPOSURE_MIN), "max": num(C.EXPOSURE_MAX),
                     "p_bonus": num(pb.P_bonus), "beta": num(pb.beta), "p_market_up": num(PB.attrs.get("P_market_up")),
                     "expected_return": num(pb.E_return), "return_q05": num(pb.r05), "return_q95": num(pb.r95)},
        "active_es": {"with_sleeve": num(g["es_full"]), "replica_only": num(g["es_zero"]), "limit": num(g["budget"]),
                      "target_book": num(g["es_tgt_active"]), "current_book": num(g["es_cur_active"])},
        "orders": {"count": int(g["ntr"]), "turnover": num(g["turnover"]), "cash_after": num(g["cash_after"])},
        "constraints_status": g["worst_lim"],
        "tables": {"constraints": table(g["LIM"]), "bonus": table(g["PBf"]), "start_level": table(g["start_sens"]),
                   "trades": table(g["TRf"]), "risk": table(g["RISK"]), "legs": table(g["LEGf"]),
                   "positions": table(g["EULf"]), "stress": table(g["STf"])},
        "targets": targets.get("targets", {}),
    }
    save(OUT_JSON, result)

    # the model's own dashboard and figures, as its author reads them
    src = MODEL / "output" / str(asof)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for f in sorted(src.glob("*")):
        if f.suffix in (".html", ".png"):
            dst = OUT_DIR / f.name
            if not dst.exists() or dst.read_bytes() != f.read_bytes():
                shutil.copyfile(f, dst)

    # target weights for the site, unless the portfolio manager has taken them over by hand
    current = load(TARGETS, {}) or {}
    if current.get("source") == "manual":
        print("content/targets.json says source = manual: target weights left as they are")
    elif targets.get("targets"):
        save(TARGETS, {"note": targets.get("note", "") + " Written by scripts/run_igfinal.py on every run of the model. "
                               "To set the weights by hand instead, change source to \"manual\".",
                       "source": "igfinal", "generated": targets.get("generated"), "targets": targets["targets"]})

    tail = [ln for ln in log.getvalue().splitlines() if ln.startswith(" ")][:4]
    print("allocation model: ok\n" + "\n".join(tail))


if __name__ == "__main__":
    main()
