"""data.py - price layer with a frozen / live switch.
   "live"   : download from Yahoo up to the last completed session and save a dated snapshot
   "frozen" : read a snapshot (FROZEN_FILE in config.py, or the latest one)
Choose in config.py (PRICE_SOURCE) or per run:  python3 run_dashboard.py frozen
Prices are split-adjusted closes WITHOUT dividends, comparable with the S&P 500 price index."""
import glob, os, sys, warnings
from datetime import date, datetime
import pandas as pd
import config as C


def pick_source(default=None):
    a = [x.lower() for x in sys.argv[1:] if x.lower() in ("live", "frozen")]
    return a[0] if a else (default or C.PRICE_SOURCE)


def latest_snapshot():
    f = sorted(glob.glob("data/snapshots/prices_*.csv"))
    if not f:
        raise SystemExit("No snapshot in data/snapshots/. Run once with the 'live' source.")
    return f[-1]


def load_prices(symbols, source=None):
    source = source or pick_source()
    symbols = list(dict.fromkeys(symbols))
    if source == "frozen":
        f = C.FROZEN_FILE or latest_snapshot()
        d = pd.read_csv(f, index_col=0, parse_dates=True)
        miss = [s for s in symbols if s not in d.columns]
        if miss:
            raise SystemExit(f"Not in the frozen file {f}: {', '.join(miss)}. Use the live source.")
        P = d[symbols].astype(float)
        P.attrs["origin"] = f"frozen prices ({f}), last date {P.index[-1].date()}"
        return P
    import yfinance as yf
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        raw = yf.download(symbols, start=C.HISTORY_FROM, auto_adjust=False, progress=False, threads=True)
    P = raw["Close"].reindex(columns=symbols)
    P.index = pd.to_datetime(P.index).tz_localize(None)
    failed = [s for s in symbols if P[s].notna().sum() == 0]
    if failed:
        raise SystemExit("Download failed for " + ", ".join(failed) + ". Nothing is simulated in its place. Retry, or run with 'frozen'.")
    try:
        from zoneinfo import ZoneInfo
        ny_hour = datetime.now(ZoneInfo("America/New_York")).hour
    except Exception:
        ny_hour = 0
    if ny_hour < 17:                                    # completed sessions only
        P = P[P.index.date < date.today()]
    # Yahoo's ^VIX series carries rows for days the stock market was closed. Keep only days on which the
    # S&P 500 traded, otherwise the forward fill below would create days with a zero return for every stock.
    if C.BENCH in P.columns:
        P = P[P[C.BENCH].notna()]
    P = P.ffill()
    if (date.today() - P.index[-1].date()).days > 5:
        warnings.warn(f"Last price date is {P.index[-1].date()}: data look stale.")
    os.makedirs("data/snapshots", exist_ok=True)
    f = f"data/snapshots/prices_{P.index[-1].date()}.csv"
    P.to_csv(f, index_label="Date")
    P.attrs["origin"] = f"live Yahoo Finance prices, last date {P.index[-1].date()} (copy saved as {f})"
    return P
