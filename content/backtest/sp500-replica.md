---
title: S&P 500 replica, the 50 largest companies without NVIDIA
author: Riccardo
updated: 2026-11-16
period: Dec 2016 to Nov 2026, weekly
equity_csv: sp500-replica.csv
Annual return: 17.3%
Benchmark annual return: 15.0%
Volatility: 17.8% (index 17.2%)
Max drawdown: −28.5% (index −31.7%)
Beta: 1.03
Tracking error: 4.7% a year
---
**The rule.** Hold the 50 largest companies in the S&P 500, leaving out NVIDIA, at their index weights scaled up to 100%. The portfolio is rebuilt at the end of every month with the weights of that day and held for one month. The benchmark is the S&P 500 with dividends reinvested. This is the method behind the 70% replica of our plan, and the portfolio we hold after the IPO sleeve is sold.

**What it shows.** Over almost ten years (119 monthly portfolios) the replica moved with the index: correlation 0.97, beta 1.03 on average and between 0.97 and 1.13 in every single year. In a typical month it ended within about 2 points of the index (from −1.8% to +2.3% in nine months out of ten). The beta is a little above 1 because the replica holds more technology and communication services than the index and almost no utilities or real estate.

**Why we use it.** We started the game behind the benchmark, so we need a replica that follows the market closely but still moves a little more than it. In about 9% of the months this replica beat the index by more than 1.88 points, the gap we had to close at the start.

**Read with care.** The test only uses companies that are in the index today, so firms that left the index or failed are missing. That makes the replica's extra return of about 2 points a year look better than it would have been: it is not an edge we count on. A version with 50 stocks spread across sectors followed the index more tightly (tracking error 3.2% a year, beta 1.00). We keep it as the alternative if we are ahead of the benchmark and want to protect the lead.

Full study and code: `research/replica_study.py` in our repository.
