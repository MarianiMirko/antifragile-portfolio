# Changes to the toolkit since the copy received on 15 November 2026

The toolkit in this folder is Lorenzo's `IGfinal_py`. These are the only differences from the files he sent.
All follow decisions taken by the portfolio manager on 15 November; each can be undone in `config.py`.

| Decision | `config.py` | `run_dashboard.py` |
|---|---|---|
| No early exit: the sleeve is held to the IPO day even if the fund gets ahead | `EXIT_TRIGGER = None` (was `0.005`) | the trigger is skipped when it is `None`; the texts say "no early exit" |
| The sleeve is sold on the IPO day itself, Thursday 19 November, after the New York open, even if the IPO is postponed | `LAST_SLEEVE_CLOSE = date(2026, 11, 18)`, used in `PHASES`: the run on the close of 18 November already lists the sale | none |
| Always fully invested | `FULLY_INVESTED = True` | the exposure is set to the top of the band after the simulation, which is still run and shown |
| Orders under $10,000 are not placed | `MIN_ORDER_USD = 10_000` | target shares stay at current shares when the order would be smaller |
| Oracle leaves the replica (19 Nov): the next-largest company takes its place among the 50 | `REPLICA_EXCLUDE = ["NVDA", "ORCL"]` | none |
| Berkshire Hathaway held at 10% of the fund as a hedge (19 Nov); the replica fills the other 90% | `FIXED_WEIGHTS = {"BRK-B": 0.10}` | after the replica weights are built, the fixed names are set to their weight and the rest is scaled to fill the remainder; one line in the dashboard text |
| Berkshire is never sold to bring it back to 10% (20 Nov) | `FIXED_NO_SELL = ["BRK-B"]` | after the small-order rule, target shares of these names are never below current shares |
| Names sold since the previous run keep their prices (19 Nov fix: the trade log failed on ORCL after it left the replica) | none | `universe` also includes the names in `state/last_holdings.csv` |
| The replica of the team's study in both phases, pending the research in `research/` | `REPLICA_HOLD = "index"` (was `"min_te"`) | none |

`lib.py`, `data.py`, `html_kit.py`, `validate.py`, `crosscheck.py` and the files in `input/` are unchanged.
