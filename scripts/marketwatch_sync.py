"""Save one reading of the MarketWatch game into the data files of the site.

MarketWatch needs a login, so the pages are read in a browser (by Claude, on the portfolio
manager's computer). The reading is passed to this script as one JSON file and the script writes

    data/holdings.json       account totals and open positions
    data/transactions.json   one entry per executed order
    data/leaderboard.json    our rank and every participant's net worth, as numbers only

Usage
    python scripts/marketwatch_sync.py reading.json
    python scripts/marketwatch_sync.py reading.json --check    # validate, write nothing

The reading
    {
      "as_of": "2026-11-16T22:20:00+01:00",            optional, default: now
      "account": {"net_worth": 0, "cash": 0, "buying_power": 0, "cash_borrowed": 0, "short_reserve": 0},
      "positions": [{"ticker": "AAPL", "name": "Apple Inc.", "shares": 100, "avg_cost": 250.1, "last_price": 268.0}],
      "transactions": [{"date": "2026-11-16T10:45:00", "ticker": "AAPL", "side": "buy", "shares": 100, "price": 250.1}],
      "ranking": [{"rank": 1, "net_worth": 10019820.04, "me": false}, {"rank": null, "net_worth": 10000000, "me": true}]
    }

"transactions" is the complete history shown by MarketWatch, or null to leave the file as it is.
"ranking" is every row of the rankings table, or null to leave the file as it is. A date without
a time zone is read as New York time, which is how MarketWatch shows it.

The site is public. A ranking row may hold only "rank", "net_worth" and "me": anything else,
a name above all, stops the script before a file is written.
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
SIDES = {"buy", "sell", "short", "cover"}
ACCOUNT_KEYS = ("net_worth", "cash", "buying_power", "cash_borrowed", "short_reserve")
RANKING_KEYS = {"rank", "net_worth", "me"}


class ReadingError(ValueError):
    pass


def number(value, what, allow_none=False):
    if value is None and allow_none:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ReadingError(f"{what} must be a number, got {value!r}")
    return float(value)


def load(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def save(path, obj):
    Path(path).write_text(json.dumps(obj, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def clean_account(raw):
    if not isinstance(raw, dict):
        raise ReadingError("'account' is missing")
    acc = {k: number(raw.get(k), f"account.{k}", allow_none=k not in ("net_worth", "cash")) for k in ACCOUNT_KEYS}
    if acc["net_worth"] <= 0:
        raise ReadingError("account.net_worth must be positive")
    return acc


def clean_positions(raw):
    out = []
    for i, p in enumerate(raw or []):
        ticker = str(p.get("ticker", "")).strip().upper()
        if not ticker:
            raise ReadingError(f"positions[{i}] has no ticker")
        shares = number(p.get("shares"), f"positions[{i}].shares")
        if shares == 0:
            continue
        out.append({
            "ticker": ticker, "name": str(p.get("name") or ticker).strip(), "shares": shares,
            "avg_cost": number(p.get("avg_cost"), f"positions[{i}].avg_cost", allow_none=True),
            "last_price": number(p.get("last_price"), f"positions[{i}].last_price", allow_none=True),
        })
    return sorted(out, key=lambda p: p["ticker"])


def clean_transactions(raw):
    out = []
    for i, t in enumerate(raw):
        side = str(t.get("side", "")).strip().lower()
        if side not in SIDES:
            raise ReadingError(f"transactions[{i}].side must be one of {sorted(SIDES)}, got {t.get('side')!r}")
        date = str(t.get("date", "")).strip()
        try:
            datetime.fromisoformat(date)
        except ValueError:
            raise ReadingError(f"transactions[{i}].date is not an ISO date and time: {date!r}") from None
        shares, price = number(t.get("shares"), f"transactions[{i}].shares"), number(t.get("price"), f"transactions[{i}].price")
        if shares <= 0 or price <= 0:
            raise ReadingError(f"transactions[{i}] needs positive shares and price")
        ticker = str(t.get("ticker", "")).strip().upper()
        if not ticker:
            raise ReadingError(f"transactions[{i}] has no ticker")
        out.append({"date": date, "ticker": ticker, "side": side, "shares": shares, "price": price})
    return sorted(out, key=lambda t: t["date"])


def clean_ranking(raw):
    rows = []
    for i, r in enumerate(raw):
        extra = set(r) - RANKING_KEYS
        if extra:
            raise ReadingError(f"ranking[{i}] holds {sorted(extra)}: only rank, net_worth and me are allowed (no names)")
        rank = r.get("rank")
        if rank is not None and (isinstance(rank, bool) or not isinstance(rank, int) or rank < 1):
            raise ReadingError(f"ranking[{i}].rank must be a whole number or null")
        if not isinstance(r.get("me", False), bool):
            raise ReadingError(f"ranking[{i}].me must be true or false")
        rows.append({"rank": rank, "net_worth": number(r.get("net_worth"), f"ranking[{i}].net_worth"), "me": bool(r.get("me", False))})
    if sum(r["me"] for r in rows) != 1:
        raise ReadingError("the ranking must mark exactly one row as ours")
    return rows


def main():
    ap = argparse.ArgumentParser(description="Save a MarketWatch reading into data/.")
    ap.add_argument("reading", help="JSON file with the reading, or - for standard input")
    ap.add_argument("--check", action="store_true", help="validate and report, write nothing")
    ap.add_argument("--allow-fewer-transactions", action="store_true",
                    help="accept a history shorter than the one already saved")
    ap.add_argument("--data-dir", default=str(ROOT / "data"), help=argparse.SUPPRESS)
    args = ap.parse_args()

    cfg = load(ROOT / "config" / "fund.json", {})
    tz = ZoneInfo(cfg.get("display_timezone", "Europe/Amsterdam"))
    data = Path(args.data_dir)
    text = sys.stdin.read() if args.reading == "-" else Path(args.reading).read_text(encoding="utf-8")

    try:
        reading = json.loads(text)
        as_of = reading.get("as_of") or datetime.now(tz).replace(second=0, microsecond=0).isoformat()
        when = datetime.fromisoformat(as_of)
        if when.tzinfo is None:
            raise ReadingError("as_of needs a time zone, for example 2026-11-16T22:20:00+01:00")
        account = clean_account(reading.get("account"))
        positions = clean_positions(reading.get("positions"))
        transactions = None if reading.get("transactions") is None else clean_transactions(reading["transactions"])
        ranking = None if reading.get("ranking") is None else clean_ranking(reading["ranking"])

        old_tx = load(data / "transactions.json", {}).get("transactions", [])
        if transactions is not None and len(transactions) < len(old_tx) and not args.allow_fewer_transactions:
            raise ReadingError(f"the reading has {len(transactions)} transactions but {len(old_tx)} are already saved: "
                               "the history was probably read only in part")
        if positions and transactions is not None and not transactions:
            raise ReadingError("there are open positions but no transactions: the history was not read")
    except (ReadingError, json.JSONDecodeError) as err:
        print(f"READING REJECTED, nothing written: {err}")
        return 2

    ours = next((r for r in ranking if r["me"]), None) if ranking else None
    old_holdings = load(data / "holdings.json", {})
    rank = ours["rank"] if ours else old_holdings.get("rank")

    holdings = {
        "note": "Written by the MarketWatch sync. Do not edit by hand.",
        "as_of": as_of, "source": "marketwatch", "game": cfg.get("marketwatch_game"),
        **account, "rank": rank, "positions": positions,
    }
    files = {"holdings.json": holdings}
    notes = []

    if transactions is not None:
        files["transactions.json"] = {
            "note": "Written by the MarketWatch sync. One entry per executed order. side is buy, sell, short or cover.",
            "transactions": transactions,
        }
        if len(transactions) != len(old_tx):
            notes.append(f"transactions: {len(old_tx)} -> {len(transactions)}")

    if ranking is not None:
        old_board = load(data / "leaderboard.json", {})
        day = when.astimezone(tz).date().isoformat()
        history = [h for h in old_board.get("history", []) if h.get("date") != day] + [{"date": day, "rank": ours["rank"]}]
        files["leaderboard.json"] = {
            "note": "Written by the MarketWatch sync. Other participants are stored as values only, without names.",
            "as_of": as_of, "players": len(ranking), "our_rank": ours["rank"], "our_net_worth": ours["net_worth"],
            "field": sorted((r["net_worth"] for r in ranking), reverse=True),
            "history": sorted(history, key=lambda h: h["date"]),
        }
        if abs(ours["net_worth"] - account["net_worth"]) > 0.005:
            notes.append(f"net worth differs between portfolio page ({account['net_worth']:,.2f}) "
                         f"and rankings page ({ours['net_worth']:,.2f})")

    long_value = sum(p["shares"] * p["last_price"] for p in positions if p["last_price"] is not None)
    if positions and abs(account["cash"] + long_value - (account["cash_borrowed"] or 0) - account["net_worth"]) > 0.005 * account["net_worth"]:
        notes.append("cash plus positions does not add up to the net worth (short positions or stale prices?)")

    if not args.check:
        for name, obj in files.items():
            save(data / name, obj)

    print(("CHECK ONLY, nothing written. " if args.check else "Saved. ") +
          f"Net worth {account['net_worth']:,.2f}, cash {account['cash']:,.2f}, {len(positions)} positions, "
          f"{len(transactions) if transactions is not None else len(old_tx)} transactions, "
          f"rank {rank if rank else 'not ranked'}" + (f" of {len(ranking)}" if ranking else "") + ".")
    for n in notes:
        print("NOTE:", n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
