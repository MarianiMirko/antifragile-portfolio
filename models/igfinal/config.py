"""config.py - Investment Game IIM 2026/27 (case 1). Every assumption lives here."""
from datetime import date

# ---- Price source -----------------------------------------------------------
PRICE_SOURCE = "live"        # "live" = Yahoo up to the last close (saves a dated snapshot)
                             # "frozen" = read a snapshot, results are reproducible
FROZEN_FILE = None           # None = latest file in data/snapshots/, or a path to a specific one
HISTORY_FROM = "2017-01-01"  # history downloaded in live mode (validate.py needs several years)

# ---- Game parameters --------------------------------------------------------
INITIAL_CAPITAL = 1e7
GAME_START = date(2026, 11, 9)
FIRST_TRADE = date(2026, 11, 16)   # the team starts trading on Monday 16 Nov; in cash until then
GAME_END = date(2026, 12, 17)      # game closes 18 Dec 13:00 CET = 07:00 ET: last close that counts is 17 Dec
SP_START_LEVEL = 7422.24           # S&P 500 OPEN of Mon 9 Nov: the level behind the "1.88% behind" of the
                                   # replica report. CONFIRM with the lecturer.
SP_START_ALTERNATIVES = {"Open 9 Nov": 7422.24, "Close 6 Nov": 7376.86, "Close 9 Nov": 7549.94}
NET_WORTH_OVERRIDE = None          # paste MarketWatch "Net Worth" if it differs from cash + shares x price
CASH_RATE_ANN = 0.0                # interest MarketWatch pays on cash (check the game settings)
HOLIDAYS = [date(2026, 11, 26), date(2026, 12, 25)]
BENCH = "^GSPC"
VOL_INDEX = "^VIX"

# ---- S&P 500 replica (from the team's replica study, folder "Replica S&P 500") --
#   "index"  : the N largest at their index weights, rescaled to 100%. Out-of-sample beta close to 1
#              (0.99 in the replica study), tracking error about 5% a year. Used while we need to catch up.
#   "min_te" : the same N names with weights that minimise tracking error. Tracking error about 3.2-3.5%,
#              but beta about 0.93-0.96 out of sample. Used once there is a lead to hold.
INDEX_WEIGHTS_FILE = "input/sp500_index_weights.csv"   # SPY holdings of 12 Nov 2026, NVIDIA already left out
REPLICA_N = 50
REPLICA_EXCLUDE = ["NVDA"]
REPLICA_CATCH_UP = "index"     # while the sleeve is on
REPLICA_HOLD = "index"         # after the sleeve is sold. Was "min_te"; the portfolio manager asked on 15 Nov for the replica
                               # of the team's study in both phases, pending the result of the research in research/
W_MIN, W_MAX = 0.005, 0.15     # bounds for the "min_te" weights
REPLICA_LOOKBACK = 504

# ---- Speculative sleeve until the IPO, then pure S&P 500 replica --------------
SLEEVE_SIZE = 0.30
IPO_DATE = date(2026, 11, 19)  # expected first trading day (press reports). The run made on the close of
                               # this date switches the target to the pure replica.
# Weights INSIDE the sleeve (rescaled to sum to 1). Default: equal per name.
SLEEVE = {"AMD": 1, "ASML": 1, "MSFT": 1, "GOOGL": 1, "AMZN": 1, "META": 1, "PLTR": 1, "BABA": 1}
_SW = "Software (MSFT, GOOGL, AMZN, META)"
THEMES = {"AMD": "Production (AMD)", "ASML": "Proxy (ASML)", "MSFT": _SW, "GOOGL": _SW, "AMZN": _SW, "META": _SW,
          "PLTR": "Government (PLTR)", "BABA": "China / HK (BABA)"}
NOT_IN_SP500 = ["ASML", "BABA"]   # US-listed, but not index constituents: check they are allowed
# Portfolio manager, 15 Nov: the sleeve is sold on the IPO day itself (Thu 19 Nov) after the New York open, even if
# the IPO is postponed. The run made on the close of LAST_SLEEVE_CLOSE therefore already shows the sale in its trade list.
LAST_SLEEVE_CLOSE = date(2026, 11, 18)
PHASES = [(GAME_START, 1.00, "Speculative sleeve on, until the IPO"),
          (LAST_SLEEVE_CLOSE, 0.00, "Sleeve sold on the IPO day (Thu 19 Nov, after the New York open): S&P 500 replica only")]

# ---- Risk model ---------------------------------------------------------------
CONF = 0.975        # ES level
HORIZON = 5         # risk horizon, trading days (square-root-of-time; checked in validate.py)
RISK_WINDOW = 504   # daily scenarios
LAMBDA = 0.94       # EWMA decay for volatility scaling
N_BOOT = 500        # bootstrap replications for the intervals

# ---- Exit rule and monitoring limits ---------------------------------------------
# Once the book is EXIT_TRIGGER ahead of the dual benchmark, sell the sleeve and hold the replica.
# The exit is permanent (recorded in state/sleeve_exit.csv; delete that file to re-open the sleeve).
EXIT_TRIGGER = None        # was 0.005. Portfolio manager, 15 Nov: no early exit, the sleeve is held to the IPO day. A number
                           # (0.005 = half a point) brings the early exit back.
ACTIVE_ES_LIMIT = 0.04     # monitoring limit, 5-day 97.5% ES of (portfolio - S&P), sleeve on
REPLICA_ES_LIMIT = 0.03    # the same, replica only

# ---- Equity exposure decision (dual benchmark simulation) ---------------------
EXPOSURE_MIN, EXPOSURE_MAX = 0.40, 1.00
FULLY_INVESTED = True      # portfolio manager, 15 Nov: always 100% invested. The simulation below is still run and shown,
                           # but it no longer sets a cash share. False brings the cash rule back.
MIN_ORDER_USD = 10_000     # portfolio manager, 15 Nov: an order smaller than this is not placed (commission of 10 per order)
N_SIM = 20000
VIX_HAIRCUT = 0.80         # realised vol has averaged ~0.8 x VIX (validate.py); 1 = use VIX as is
MARKET_DRIFT_ANN = 0.06    # expected S&P return per year used in the simulation (0 = no view)
ALPHA_VIEW = 0.0           # expected extra return of the book to game end (0 = no view)

# ---- Investment-plan constraints, checked on every run ------------------------
LIMITS = dict(max_name=0.15, max_tickers=60, max_gross_short=0.00, min_cash=0.0, warn=0.90)
