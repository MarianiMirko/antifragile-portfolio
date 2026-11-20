## What we believe

Our benchmark is max(0; S&P 500): beating it earns a bonus, missing it costs nothing. If the index ends below its start level, the hurdle becomes 0% and a fully invested equity fund will almost surely miss it anyway, so extra losses in a falling market cost us little, while missing a rally costs the bonus. We therefore follow the index closely with a beta slightly above 1, and we do not claim an edge in picking stocks.

## How the portfolio is built

- **Core: a replica of the S&P 500.** The 50 largest companies of the index at their index weights, rescaled to 100%. NVIDIA is left out because of its very high volatility (and since 19 November Oracle too, replaced by Citigroup). Average beta 1.04 and tracking error 4.8% a year over ten years of monthly tests.
- **Berkshire Hathaway at 10% of the fund** since 19 November, as a defensive position; the replica fills the other 90%.
- **Satellite, 16 to 19 November only:** 30% of the fund in eight AI stocks linked to the Anthropic IPO (AMD, ASML, MSFT, GOOGL, AMZN, META, PLTR, BABA, 3.75% each), sold at the New York open on the debut day.
- **Rule of 20 November:** with a lead over the benchmark of at least 0.5 points we would switch to a sector-balanced replica (beta about 1.00, tracking error 3.2%); otherwise we keep the 50 largest. At the close of 19 November we were 3.17 points behind, so we keep the 50 largest.

## How we decide

1. **Model.** Every evening at 23:30 CET Lorenzo's model recalculates risk, target weights and the list of orders on closing prices.
2. **News, macro and ESG.** Andrea follows the news on our holdings, the macro data and ESG events.
3. **Decision.** The portfolio manager approves every order one by one; each trade is recorded with its reason in the trade log.

## Risk limits and response

Our main risk measure is the 5-day 97.5% expected shortfall of active returns (fund minus S&P 500), with a limit of 4% while the IPO sleeve was held and 3% for the replica. Other limits: at most 15% in one stock, at most 60 stocks, no short positions and no borrowed cash. A limit shows a warning at 90% of its level. A breach is fixed before any other trade: a stock above its limit is trimmed back to its target, and if the expected shortfall is too high the positions that contribute most to it are sold until it is back inside.

## Alert levels

- **Green:** data and earnings in line, every limit respected. Hold and wait for the weekly rebalance.
- **Amber:** a macro surprise, a regulatory or ESG shock on one of the ten largest positions, active risk within 0.3 points of its limit, or a stock above 14%. Team risk review before the next New York open.
- **Red:** a limit breached or cash borrowed. Corrective market order at the next open, approved by the portfolio manager and logged.

## ESG

We do not exclude whole sectors, because that would widen our tracking error. Fossil fuels, tobacco and defence stay at index weight, governance and data-centre power demand are followed as financial risks, and leaving out NVIDIA and selling Alibaba removed the two names with the highest governance risk.

## Rebalancing

From 27 November the fund is brought back to the model's target weights every Friday morning, always fully invested. Orders below USD 10,000 (0.1% of the fund) are not placed. Only market orders exist in the game: no stop-loss or limit orders.
