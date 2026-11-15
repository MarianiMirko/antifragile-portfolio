"""Data access shared by the research scripts.

In GitHub Actions the stock prices come from the fund's private database (Supabase, table
prices_daily: closing prices adjusted for splits and dividends) and everything the database
does not hold (index levels, opening prices, tickers outside the S&P 500) from Yahoo Finance.

For a quick local check without network, set RESEARCH_TEST to a CSV of prices (dates in the
first column, one column per ticker, ^GSPC included): the scripts then run on that file alone.
"""
import io
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
RESULTS = HERE / "results"
TEST_FILE = os.environ.get("RESEARCH_TEST")
SPY_HOLDINGS = "https://www.ssga.com/us/en/intermediary/etfs/library-content/products/fund-data/etfs/us/holdings-daily-us-en-spy.xlsx"


def log(*a):
    print(*a, flush=True)


# ---------------------------------------------------------------- database
def _get(session, url, params, headers, tries=5):
    for k in range(tries):
        try:
            r = session.get(url, params=params, headers=headers, timeout=60)
            if r.status_code == 200:
                return r.json()
            err = f"HTTP {r.status_code}"
        except Exception as exc:                      # network hiccup
            err = type(exc).__name__
        if k == tries - 1:
            raise RuntimeError(f"database request failed: {err}")
        time.sleep(2 * (k + 1))


def db_prices(start, tickers=None):
    """(prices, securities): adjusted closes from the database, dates x tickers, and the securities table."""
    import requests
    base = os.environ["SUPABASE_URL"].rstrip("/") + "/rest/v1/"
    key = os.environ["SUPABASE_SECRET_KEY"]
    headers = {"apikey": key, "Authorization": "Bearer " + key}
    s = requests.Session()
    sec = pd.DataFrame(_get(s, base + "securities", {"select": "id,ticker,name,sector,first_date,last_date", "asset_class": "eq.US stock",
                                                     "order": "id.asc", "limit": "2000"}, headers))
    if tickers is not None:
        sec = sec[sec.ticker.isin(tickers)]

    def one(row):
        sess, out, off = requests.Session(), [], 0
        while True:
            page = _get(sess, base + "prices_daily", {"select": "price_date,close", "security_id": f"eq.{row.id}", "price_date": f"gte.{start}",
                                                      "order": "price_date.asc", "limit": "1000", "offset": str(off)}, headers)
            out.extend(page)
            if len(page) < 1000:
                break
            off += 1000
        return row.ticker, pd.Series({r["price_date"]: r["close"] for r in out}, dtype=float)

    t0 = time.time()
    with ThreadPoolExecutor(12) as pool:
        cols = dict(pool.map(one, list(sec.itertuples())))
    px = pd.DataFrame(cols); px.index = pd.to_datetime(px.index); px = px.sort_index()
    log(f"database: {px.shape[1]} stocks, {px.shape[0]} days from {px.index[0].date()} to {px.index[-1].date()}, "
        f"{int(px.notna().sum().sum()):,} prices in {time.time() - t0:.0f}s")
    return px, sec.set_index("ticker")


# ---------------------------------------------------------------- Yahoo
def yahoo(symbols, start, fields=("Open", "Close")):
    """dict field -> DataFrame (dates x symbols), prices adjusted for splits and dividends."""
    import yfinance as yf
    symbols = list(dict.fromkeys(symbols)); last = None
    for attempt in range(4):
        try:
            raw = yf.download(symbols, start=start, auto_adjust=True, progress=False, group_by="column", threads=False)
            if raw is not None and not raw.empty:
                out = {}
                for f in fields:
                    d = raw[f] if isinstance(raw.columns, pd.MultiIndex) else raw[[f]].rename(columns={f: symbols[0]})
                    d.index = pd.to_datetime(d.index).tz_localize(None); out[f] = d.reindex(columns=symbols)
                missing = [s for s in symbols if out[fields[-1]][s].notna().sum() == 0]
                if not missing or attempt == 3:
                    if missing:
                        log("Yahoo has no data for:", ", ".join(missing))
                    return out
                last = "missing " + ", ".join(missing)
        except Exception as exc:
            last = f"{type(exc).__name__}: {exc}"
        log(f"Yahoo attempt {attempt + 1} incomplete ({last}); trying again"); time.sleep(5 * (attempt + 1))
    raise RuntimeError("Yahoo download failed: " + str(last))


# ---------------------------------------------------------------- index weights
def index_weights(tickers):
    """Today's S&P 500 weights (fractions) for the given tickers: SPY holdings, or market values from Yahoo."""
    try:
        import requests
        r = requests.get(SPY_HOLDINGS, headers={"User-Agent": "Mozilla/5.0 (student research project)"}, timeout=60); r.raise_for_status()
        raw = pd.read_excel(io.BytesIO(r.content), header=None)
        top = next(i for i in range(len(raw)) if "Ticker" in set(map(str, raw.iloc[i].values)))
        h = pd.read_excel(io.BytesIO(r.content), skiprows=top)
        h = h[h["Ticker"].notna() & h["Weight"].notna()]
        h["Ticker"] = h["Ticker"].astype(str).str.strip().str.upper().str.replace("-", ".", regex=False)
        w = h.groupby("Ticker")["Weight"].sum().astype(float)
        w = w.rename({"GOOG": "GOOGL", "FOX": "FOXA", "NWS": "NWSA"}).groupby(level=0).sum()      # second share classes join the first
        w = w.reindex(tickers).dropna()
        if len(w) > 400:
            log(f"index weights: SPY holdings, {len(w)} companies, {w.sum():.1f}% of the fund covered")
            return (w / w.sum()), "SPY holdings published by State Street"
        log(f"SPY holdings matched only {len(w)} tickers; using market values instead")
    except Exception as exc:
        log(f"SPY holdings not available ({type(exc).__name__}: {str(exc)[:80]}); using market values instead")
    import yfinance as yf

    def cap(t):
        for _ in range(3):
            try:
                v = yf.Ticker(t.replace(".", "-")).fast_info["market_cap"]
                if v and v > 0:
                    return t, float(v)
            except Exception:
                time.sleep(1)
        return t, np.nan
    with ThreadPoolExecutor(8) as pool:
        caps = pd.Series(dict(pool.map(cap, tickers))).dropna()
    # one company, two share classes: Yahoo reports the whole company on each line
    for a, b in (("GOOGL", "GOOG"), ("FOXA", "FOX"), ("NWSA", "NWS")):
        if a in caps and b in caps:
            caps = caps.drop(b)
    log(f"index weights: market values from Yahoo, {len(caps)} companies")
    return caps / caps.sum(), "market values from Yahoo Finance (not float-adjusted)"


# ---------------------------------------------------------------- local test file
def test_prices():
    d = pd.read_csv(TEST_FILE, index_col=0, parse_dates=True)
    d.columns = [c.replace("-", ".") if not c.startswith("^") else c for c in d.columns]
    return d.astype(float)


def pct(x, d=1):
    return "n/a" if x is None or not np.isfinite(x) else f"{100 * x:.{d}f}%"
