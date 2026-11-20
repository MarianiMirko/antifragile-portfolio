---
title: S&P 500 replica
author: Riccardo
updated: 2026-11-19
period: Dec 2016 to Nov 2026, weekly
equity_csv: sp500-replica.csv
Annual return: 17.3%
S&P 500 annual return: 15.0%
Beta: 1.03
Tracking error: 4.7%
Max drawdown: −30.1%
---
**The rule.** Hold the 50 largest companies in the S&P 500, leaving out NVIDIA, at their index weights scaled up to 100%. The portfolio is rebuilt at the end of every month with the weights of that day and held for one month. The benchmark is the S&P 500 with dividends reinvested. This is the method behind the 70% replica of our plan, and the portfolio we hold after the IPO sleeve is sold.

**How the 50 were chosen.** All S&P 500 constituents are ranked by their weight in the index (holdings of the SPDR S&P 500 ETF, SPY). NVIDIA, 6.1% of the index, would be about 10% of the replica and, with its very high volatility, too influential: without it the replica tracks the index better (tracking error 4.8% instead of 5.1%, beta 1.04 instead of 1.07). Fifty is a trade-off between tracking error (7.3% with 20 stocks, 4.8% with 50, 3.3% with 100) and the cost of orders, within our limit of 60 stocks.

**What it shows.** Over almost ten years (119 monthly portfolios) the replica moved with the index: correlation 0.97, beta 1.03 on average, worst fall −30.1% against −33.8% for the index and between 0.97 and 1.13 in every single year. In a typical month it ended within about 2 points of the index (from −1.8% to +2.3% in nine months out of ten). The beta is a little above 1 because the replica holds more technology and communication services than the index and almost no utilities or real estate.

**Why we use it.** We started the game behind the benchmark, so we need a replica that follows the market closely but still moves a little more than it. In about 9% of the months this replica beat the index by more than 1.88 points, the gap we had to close at the start.

**Read with care.** The test only uses companies that are in the index today, so firms that left the index or failed are missing. That makes the replica's extra return of about 2 points a year look better than it would have been: it is not an edge we count on. A version with 50 stocks spread across sectors followed the index more tightly (tracking error 3.2% a year, beta 1.00). We keep it as the alternative if we are ahead of the benchmark and want to protect the lead.
