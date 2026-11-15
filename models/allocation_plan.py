"""The allocation model that steers the fund (toolkit in models/igfinal, written by Lorenzo).

The model runs before every site update (scripts/run_igfinal.py) and leaves its results in
data/igfinal.json. This file only lays those results out for the Risk page: where we stand against
max(0, S&P 500), the probability of the bonus, the phase of the plan, the constraints and the
trade list. To change the plan, edit models/igfinal/config.py.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SIGNAL = {"BREACH": "alert", "WARNING": "caution", "OK": "normal"}
TRADE_COLUMNS = ["Ticker", "Last close", "Shares now", "Target shares", "Order, shares", "Order, USD",
                 "Weight now, %", "Target weight, %", "Weight in the replica, %", "Action"]


def pct(x, d=2, sign=False):
    if x is None:
        return "n/a"
    return f"{100 * x:+.{d}f}%" if sign else f"{100 * x:.{d}f}%"


def flag_status(tbl):
    """Colour the Status column of a table that has one."""
    cols = tbl["columns"]
    if "Status" not in cols:
        return tbl
    i = cols.index("Status")
    rows = [[{"v": c, "signal": SIGNAL.get(c, "normal")} if j == i else c for j, c in enumerate(r)] for r in tbl["rows"]]
    return {"columns": cols, "rows": rows}


def run(ctx):
    base = {"title": "Allocation plan: S&P 500 replica and IPO sleeve", "author": "Lorenzo, with the replica study by Riccardo"}
    try:
        d = json.loads((ROOT / "data" / "igfinal.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {**base, "description": "The model has not produced results yet. It runs with the next price update.", "metrics": []}
    if "standing" not in d:
        return {**base, "description": d.get("message") or "The model has not produced results yet.", "metrics": []}

    s, ph, rep, ex, es, t = d["standing"], d["phase"], d["replica"], d["exposure"], d["active_es"], d["tables"]
    behind = s["excess"] < 0
    breaches = [r[1] for r in t["constraints"]["rows"] if r[0] == "Current" and r[4] == "BREACH"]
    warnings = [r[1] for r in t["constraints"]["rows"] if r[0] == "Current" and r[4] == "WARNING"]
    es_use = es["target_book"] / es["limit"] if es["limit"] else 0
    if ph["exited"]:
        phase_value, phase_note = "Replica only", f"The sleeve was sold for good on {ph['exit_date']}: {ph['exit_reason']}."
    elif ph["sleeve_on"]:
        phase_value = "Sleeve on"
        phase_note = f"{pct(ph['sleeve_size'], 0)} of the fund in {', '.join(ph['sleeve'])}. "
        if ph.get("exit_trigger") is None:
            phase_note += f"The whole sleeve is sold on the IPO day ({ph['ipo_date']}), after the New York open. There is no earlier exit."
        else:
            phase_note += (f"The sleeve is sold once the fund is {pct(ph['exit_trigger'], 1)} ahead of the benchmark, or on the IPO day "
                           f"({ph['ipo_date']}), whichever comes first.")
    else:
        phase_value, phase_note = "Replica only", ph["label"] + "."
    weights = "index weights" if rep["method"] == "index" else "minimum-tracking-error weights"

    metrics = [
        {"name": "Against the benchmark, max(0, S&P 500)", "value": pct(s["excess"], 2, True), "signal": "caution" if behind else "normal",
         "comment": f"Fund {pct(s['fund_return'], 2, True)}, S&P 500 {pct(s['sp_return'], 2, True)} from the start level of "
                    f"{s['sp_start_level']:,.2f}. Closing prices of {d['asof']}."},
        {"name": "Probability of the bonus", "value": pct(ex["p_bonus"], 0),
         "comment": f"Chance of finishing above max(0, S&P 500) with {d['days_left']} trading days left, at {pct(ex['chosen'], 0)} equity. "
                    f"The S&P 500 ends above its start in {pct(ex['p_market_up'], 0)} of the simulated paths."},
        {"name": "Phase of the plan", "value": phase_value, "comment": phase_note},
        {"name": "Equity exposure", "value": pct(ex["chosen"], 0),
         "comment": ("The plan is always fully invested. " if ex.get("fully_invested") else f"Inside the {pct(ex['min'], 0)} to {pct(ex['max'], 0)} band, the rest in cash. ")
                    + f"Beta of the target book {ex['beta']:.2f}; final return between {pct(ex['return_q05'], 1, True)} and "
                      f"{pct(ex['return_q95'], 1, True)} in 90% of paths."},
        {"name": "Risk of trailing the S&P 500", "value": pct(es["target_book"]),
         "signal": "alert" if es_use > 1 else "caution" if es_use > 0.9 else "normal",
         "comment": f"Five-day expected shortfall at 97.5% of the target book against the index; limit {pct(es['limit'])}. "
                    f"The book we hold now: {pct(es['current_book'])}."},
        {"name": "Plan constraints, book we hold now", "value": d["constraints_status"].capitalize(),
         "signal": SIGNAL.get(d["constraints_status"], "normal"),
         "comment": ("In breach: " + ", ".join(breaches) + ". ") * bool(breaches) + ("Close to the limit: " + ", ".join(warnings) + ". ") * bool(warnings)
                    or "Every limit of the plan is respected."},
        {"name": "Orders to reach the target", "value": str(d["orders"]["count"]),
         "comment": f"Turnover {pct(d['orders']['turnover'], 0)} of the fund"
                    + (f"; orders below ${d['orders']['min_order_usd']:,.0f} are left out" if d["orders"].get("min_order_usd") else "")
                    + ". Nothing is traded until the portfolio manager approves each order."},
        {"name": "Replica", "value": f"{rep['names']} companies",
         "comment": f"At {weights}: the largest S&P 500 companies without {', '.join(rep['excluded']) or 'exclusions'}. Beta {rep['beta']:.2f} and tracking error "
                    f"{pct(rep['tracking_error'], 1)} a year over the last two years."},
    ]
    if d.get("status") != "ok":
        metrics.insert(0, {"name": "Model status", "value": "Waiting" if d.get("status") == "waiting" else "Not updated",
                           "signal": "caution", "comment": d.get("message") or ""})
    if ph["sleeve_on"] and ph.get("not_in_sp500"):
        metrics.append({"name": "To confirm with the lecturer", "value": " and ".join(ph["not_in_sp500"]), "signal": "caution",
                        "comment": "Listed in the US but not S&P 500 constituents, and the case names the constituents as the universe."})

    trades = {"columns": TRADE_COLUMNS, "rows": [[str(c) for c in r] for r in t["trades"]["rows"]]}
    return {
        **base,
        "description": "70% of the fund follows the S&P 500 through its 50 largest companies; 30% is a sleeve of AI and IPO-related names "
                       "held until the exit rule fires. The model checks the plan's limits, simulates the chance of finishing above "
                       "max(0, S&P 500) and writes the target weights and the trade list. It reprices at each daily close.",
        "metrics": metrics,
        "table": flag_status(t["constraints"]),
        "tables": [
            {"title": f"Trade list to reach the target ({d['orders']['count']} orders)", "table": trades,
             "note": "Whole shares at the last close; the count changes with the price on the day. Market orders only."},
            {"title": "Bonus probability by equity exposure", "table": t["bonus"],
             "note": "20,000 simulated paths to the last close of the game, built from five-day blocks of real past days."},
            {"title": "If the S&P 500 start level is a different one", "table": t["start_level"],
             "note": "The start level of the benchmark is still to be confirmed with the lecturer."},
            {"title": "Risk of the target book (five days, 97.5%)", "table": t["risk"]},
            {"title": "Where the risk of trailing the index comes from", "table": t["legs"],
             "note": "Each leg's contribution to the five-day active expected shortfall, by two allocation methods."},
            {"title": "Largest contributions by position", "table": t["positions"]},
            {"title": "Stress tests: target book against the S&P 500", "table": t["stress"],
             "note": "Historical replays hold today's target weights through the episode. The hypothetical shocks are assumptions."},
        ],
        "links": [{"label": "Open the model's full dashboard, with charts", "href": "data/igfinal/dashboard.html"}],
    }
