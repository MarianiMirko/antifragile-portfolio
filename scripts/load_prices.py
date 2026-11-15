#!/usr/bin/env python3
"""
load_prices.py - fill the private database with daily prices of the S&P 500 companies.

Runs inside GitHub Actions (workflow "Load stock prices"), never in the browser.
Needs two environment variables:
  SUPABASE_URL          the project address (public)
  SUPABASE_SECRET_KEY   the project's secret key, stored as a GitHub secret

  python scripts/load_prices.py --since 1980-01-01     full history (first run)
  python scripts/load_prices.py --days 15              only the latest days (weekly refresh)

Prices are closing prices adjusted for splits and dividends, from Yahoo Finance.
Only companies that are in the index today are included: companies that left the
index or were delisted are missing, so long backtests on this data look better
than reality (survivorship bias).
"""
import argparse
import io
import os
import sys
import time

import pandas as pd
import requests
import yfinance as yf
from supabase import create_client

WIKI = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
BATCH_TICKERS = 40
CHUNK_ROWS = 5000


def constituents():
    html = requests.get(WIKI, headers={"User-Agent": "antifragile-portfolio student project"}, timeout=60).text
    table = pd.read_html(io.StringIO(html))[0]
    out = table.rename(columns={"Symbol": "ticker", "Security": "name", "GICS Sector": "sector",
                                "GICS Sub-Industry": "industry"})[["ticker", "name", "sector", "industry"]]
    out["ticker"] = out["ticker"].str.strip().str.upper()
    return out.drop_duplicates("ticker").sort_values("ticker").reset_index(drop=True)


def with_retry(fn, tries=5):
    for attempt in range(tries):
        try:
            return fn()
        except Exception as exc:  # network hiccups and timeouts
            if attempt == tries - 1:
                raise
            wait = 3 * (attempt + 1)
            print(f"  retry in {wait}s: {type(exc).__name__}: {str(exc)[:120]}", file=sys.stderr)
            time.sleep(wait)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default=None, help="first date to load, e.g. 1980-01-01")
    ap.add_argument("--days", type=int, default=15, help="without --since: load only the last N days")
    args = ap.parse_args()
    start = args.since or (pd.Timestamp.utcnow() - pd.Timedelta(days=args.days)).strftime("%Y-%m-%d")

    db = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SECRET_KEY"])

    # securities: keep the ids already in the database, give new tickers the next free id
    comp = constituents()
    known = {r["ticker"]: r["id"] for r in with_retry(lambda: db.table("securities").select("id,ticker").execute()).data}
    next_id = max(known.values(), default=0) + 1
    rows = []
    for r in comp.itertuples():
        if r.ticker not in known:
            known[r.ticker] = next_id
            next_id += 1
        rows.append({"id": known[r.ticker], "ticker": r.ticker, "name": r.name, "sector": r.sector, "industry": r.industry})
    with_retry(lambda: db.table("securities").upsert(rows, on_conflict="id").execute())
    print(f"{len(rows)} securities, loading prices from {start}")

    total = 0
    tickers = list(comp["ticker"])
    for i in range(0, len(tickers), BATCH_TICKERS):
        batch = tickers[i:i + BATCH_TICKERS]
        symbols = {t: t.replace(".", "-") for t in batch}
        data = with_retry(lambda: yf.download(list(symbols.values()), start=start, interval="1d", auto_adjust=True,
                                              progress=False, threads=True, group_by="column"))
        if data is None or data.empty:
            print(f"  no data for batch {i // BATCH_TICKERS + 1}", file=sys.stderr)
            continue
        close = data["Close"] if isinstance(data.columns, pd.MultiIndex) else data[["Close"]].rename(columns={"Close": list(symbols.values())[0]})
        payload, stats = [], []
        for t, sym in symbols.items():
            if sym not in close.columns:
                continue
            s = close[sym].dropna()
            s = s[s > 0]
            if s.empty:
                continue
            sid = known[t]
            payload.extend({"security_id": sid, "price_date": d.strftime("%Y-%m-%d"), "close": round(float(v), 4)}
                           for d, v in s.items())
            stats.append((sid, s.index[0].strftime("%Y-%m-%d"), s.index[-1].strftime("%Y-%m-%d")))
        for j in range(0, len(payload), CHUNK_ROWS):
            chunk = payload[j:j + CHUNK_ROWS]
            with_retry(lambda: db.table("prices_daily").upsert(chunk, on_conflict="security_id,price_date",
                                                               returning="minimal").execute())
        if args.since:   # on a full load, record the span of each security
            for sid, first, last in stats:
                with_retry(lambda: db.table("securities").update({"first_date": first, "last_date": last}).eq("id", sid).execute())
        else:
            for sid, _first, last in stats:
                with_retry(lambda: db.table("securities").update({"last_date": last}).eq("id", sid).execute())
        total += len(payload)
        print(f"  {min(i + BATCH_TICKERS, len(tickers))}/{len(tickers)} tickers, {total:,} rows so far", flush=True)
        time.sleep(1)
    print(f"done: {total:,} price rows")


if __name__ == "__main__":
    main()
