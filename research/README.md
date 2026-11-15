# Research

Studies behind the fund's investment plan. They run in GitHub Actions (workflow **Research studies**)
on the fund's private database and on Yahoo Finance, and write their results to `research/results/`.

| Script | Question |
|---|---|
| `replica_study.py` | Which is the most efficient way to hold the S&P 500 without buying all its companies? |
| `ipo_event_study.py` | How did the listed "friends" of a company move in the days around its IPO? |

`ipo_events.csv` lists the IPOs and the companies tied to each one; `ipo_dates_broad.csv` is the longer
list used for the test on technology stocks as a group. Each script explains its method at the top.
