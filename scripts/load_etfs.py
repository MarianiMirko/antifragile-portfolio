#!/usr/bin/env python3
"""
load_etfs.py - add European ETFs with more than 1 billion in assets to the private database.

Runs inside GitHub Actions (workflow "Load European ETFs"). Needs SUPABASE_URL and SUPABASE_SECRET_KEY.

  python scripts/load_etfs.py --since 1980-01-01   first run: build the list, then load full history
  python scripts/load_etfs.py --days 15            refresh the ETFs already in the database

How the list is built
  1. Every ETF tradable on Xetra (Deutsche Boerse's public "all tradable instruments" file), EUR listings.
  2. Fund size ("totalAssets") from Yahoo Finance for each one.
  3. Keep those with at least 1 billion (in the fund's own currency, EUR or USD), largest first.
Loading stops before the database would exceed its row budget, so the free plan's 500 MB is never hit.
"""
import argparse
import io
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import requests
import yfinance as yf
from supabase import create_client

XETRA_FILES = [
    "https://www.xetra.com/xetra-en/allTradableInstruments.csv",
    "http://xetra.com/xetra-en/allTradableInstruments.csv",
    "https://www.cashmarket.deutsche-boerse.com/resource/blob/1528/latest/data/t7-xetr-allTradableInstruments.csv",
]
MIN_ASSETS = 1_000_000_000
MAX_TOTAL_ROWS = 6_400_000        # all price rows in the database, stocks included (about 430 MB)
BATCH_TICKERS = 40
CHUNK_ROWS = 5000
UA = {"User-Agent": "Mozilla/5.0 (antifragile-portfolio student project)"}


def with_retry(fn, tries=5):
    for attempt in range(tries):
        try:
            return fn()
        except Exception as exc:
            if attempt == tries - 1:
                raise
            time.sleep(3 * (attempt + 1))
            print(f"  retry: {type(exc).__name__}: {str(exc)[:120]}", file=sys.stderr)


def xetra_etfs():
    last = None
    for url in XETRA_FILES:
        try:
            r = requests.get(url, headers=UA, timeout=120)
            r.raise_for_status()
            text = r.content.decode("utf-8", errors="replace")
            lines = text.splitlines()
            head = next(i for i, ln in enumerate(lines[:20]) if "ISIN" in ln and "Mnemonic" in ln)
            df = pd.read_csv(io.StringIO("\n".join(lines[head:])), sep=";", dtype=str, on_bad_lines="skip")
            df.columns = [c.strip() for c in df.columns]
            print(f"instrument file: {url} ({len(df):,} rows)")
            type_col = next(c for c in df.columns if c.lower().replace(" ", "") in ("instrumenttype", "producttype"))
            etf = df[df[type_col].str.strip().str.upper().eq("ETF") & df["Currency"].str.strip().eq("EUR")]
            etf = etf[etf["Mnemonic"].notna()].drop_duplicates("ISIN")
            name_col = "Instrument" if "Instrument" in etf.columns else etf.columns[1]
            return [{"isin": r_["ISIN"].strip(), "mnemonic": r_["Mnemonic"].strip(), "name": str(r_[name_col]).strip()}
                    for _, r_ in etf.iterrows()]
        except Exception as exc:
            last = exc
            print(f"could not use {url}: {type(exc).__name__}: {str(exc)[:160]}", file=sys.stderr)
    raise SystemExit(f"No instrument file could be downloaded: {last}")


def fund_size(item):
    sym = item["mnemonic"] + ".DE"
    for attempt in range(3):
        try:
            info = yf.Ticker(sym).info or {}
            return {**item, "ticker": sym, "assets": info.get("totalAssets"), "currency": info.get("currency") or "EUR",
                    "long_name": info.get("longName") or info.get("shortName") or item["name"]}
        except Exception:
            time.sleep(2 * (attempt + 1))
    return {**item, "ticker": sym, "assets": None, "currency": "EUR", "long_name": item["name"]}


def count_rows(db):
    return with_retry(lambda: db.table("prices_daily").select("security_id", count="exact", head=True).execute()).count or 0


def load_prices(db, items, start, full, budget):
    total = 0
    for i in range(0, len(items), BATCH_TICKERS):
        batch = items[i:i + BATCH_TICKERS]
        syms = [b["ticker"] for b in batch]
        data = with_retry(lambda: yf.download(syms, start=start, interval="1d", auto_adjust=True, progress=False,
                                              threads=True, group_by="column"))
        if data is None or data.empty:
            continue
        close = data["Close"] if isinstance(data.columns, pd.MultiIndex) else data[["Close"]].rename(columns={"Close": syms[0]})
        payload, stats = [], []
        for b in batch:
            if b["ticker"] not in close.columns:
                continue
            s = close[b["ticker"]].dropna()
            s = s[s > 0]
            if s.empty:
                continue
            payload.extend({"security_id": b["id"], "price_date": d.strftime("%Y-%m-%d"), "close": round(float(v), 4)}
                           for d, v in s.items())
            stats.append((b["id"], s.index[0].strftime("%Y-%m-%d"), s.index[-1].strftime("%Y-%m-%d")))
        if budget is not None and total + len(payload) > budget:
            print(f"row budget reached after {total:,} rows: stopping before batch {i // BATCH_TICKERS + 1}")
            break
        for j in range(0, len(payload), CHUNK_ROWS):
            chunk = payload[j:j + CHUNK_ROWS]
            with_retry(lambda: db.table("prices_daily").upsert(chunk, on_conflict="security_id,price_date",
                                                               returning="minimal").execute())
        for sid, first, last in stats:
            upd = {"first_date": first, "last_date": last} if full else {"last_date": last}
            with_retry(lambda: db.table("securities").update(upd).eq("id", sid).execute())
        total += len(payload)
        print(f"  {min(i + BATCH_TICKERS, len(items))}/{len(items)} ETFs, {total:,} rows so far", flush=True)
        time.sleep(1)
    return total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default=None)
    ap.add_argument("--days", type=int, default=15)
    args = ap.parse_args()
    db = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SECRET_KEY"])
    known = with_retry(lambda: db.table("securities").select("id,ticker,asset_class").execute()).data

    if not args.since:                       # refresh only
        items = [{"id": r["id"], "ticker": r["ticker"]} for r in known if r.get("asset_class") == "European ETF"]
        start = (pd.Timestamp.utcnow() - pd.Timedelta(days=args.days)).strftime("%Y-%m-%d")
        print(f"refreshing {len(items)} ETFs from {start}")
        print(f"done: {load_prices(db, items, start, False, None):,} rows")
        return

    universe = xetra_etfs()
    print(f"{len(universe):,} ETFs listed in EUR on Xetra; reading fund sizes")
    with ThreadPoolExecutor(max_workers=6) as pool:
        sized = list(pool.map(fund_size, universe))
    have = [s for s in sized if s["assets"]]
    big = sorted([s for s in have if s["assets"] >= MIN_ASSETS], key=lambda s: -s["assets"])
    print(f"fund size found for {len(have):,} of {len(sized):,}; {len(big):,} have at least 1 billion")
    if len(have) < 0.3 * len(sized):
        raise SystemExit("Fund sizes could not be read for most ETFs (the data source is probably rate-limiting). Nothing loaded.")

    ids = {r["ticker"]: r["id"] for r in known}
    next_id = max(ids.values(), default=0) + 1
    rows = []
    for s in big:
        if s["ticker"] not in ids:
            ids[s["ticker"]] = next_id
            next_id += 1
        s["id"] = ids[s["ticker"]]
        rows.append({"id": s["id"], "ticker": s["ticker"], "name": s["long_name"], "sector": "ETF", "industry": None,
                     "asset_class": "European ETF", "currency": "EUR", "exchange": "Xetra", "isin": s["isin"],
                     "assets": s["assets"]})
    for j in range(0, len(rows), 500):
        with_retry(lambda: db.table("securities").upsert(rows[j:j + 500], on_conflict="id").execute())
    budget = MAX_TOTAL_ROWS - count_rows(db)
    print(f"{len(rows)} ETFs registered; room for {budget:,} more price rows")
    total = load_prices(db, big, args.since, True, budget)
    # drop ETFs that ended up without any price (not loaded because of the budget or missing data)
    loaded = {r["id"] for r in with_retry(lambda: db.table("securities").select("id").eq("asset_class", "European ETF")
                                           .not_.is_("last_date", "null").execute()).data}
    empty = [s["id"] for s in big if s["id"] not in loaded]
    for sid in empty:
        with_retry(lambda: db.table("securities").delete().eq("id", sid).execute())
    print(f"done: {total:,} price rows for {len(loaded)} ETFs ({len(empty)} left out)")


if __name__ == "__main__":
    main()
