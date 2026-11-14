"""Example model: EWMA volatility forecast (RiskMetrics, lambda = 0.94).

Compares each position's short-term volatility forecast with its one-year average,
and flags the names whose risk is currently running hot.
"""
import math

LAMBDA = 0.94


def ewma_vol(returns):
    var = float(returns.iloc[:20].var())
    for r in returns.iloc[20:]:
        var = LAMBDA * var + (1 - LAMBDA) * float(r) ** 2
    return math.sqrt(var * 252)


def run(ctx):
    daily, weights = ctx["daily"], ctx["weights"]
    if daily is None or not weights:
        return {"title": "EWMA volatility forecast", "author": "Example",
                "description": "Needs price history and at least one position.", "metrics": []}
    tickers = list(weights)
    rets = daily[tickers].pct_change().dropna()
    port = (rets * [weights[t] for t in tickers]).sum(axis=1)
    f_port, lr_port = ewma_vol(port), float(port.std() * math.sqrt(252))
    ratio = f_port / lr_port

    def sig(x):
        return "alert" if x > 1.5 else "caution" if x > 1.2 else "normal"

    rows = []
    for t in sorted(tickers, key=lambda k: -weights[k]):
        f, lr = ewma_vol(rets[t]), float(rets[t].std() * math.sqrt(252))
        rows.append([t, f"{weights[t] * 100:.1f}%", f"{lr * 100:.1f}%",
                     {"v": f"{f * 100:.1f}%", "signal": sig(f / lr)}, f"{f / lr:.2f}x"])
    return {
        "title": "EWMA volatility forecast",
        "author": "Example model",
        "description": "Short-term volatility forecast (EWMA, lambda 0.94) against each position's one-year average. "
                       "Above 1.2x is flagged, above 1.5x is an alert.",
        "metrics": [
            {"name": "Fund forecast volatility", "value": f"{f_port * 100:.1f}%", "signal": sig(ratio),
             "comment": f"{ratio:.2f}x its one-year average of {lr_port * 100:.1f}%"},
            {"name": "Positions running hot", "value": str(sum(1 for r in rows if r[3]['signal'] != 'normal')),
             "signal": "normal", "comment": "forecast above 1.2x the one-year average"},
        ],
        "table": {"columns": ["Ticker", "Weight", "1-year vol", "Forecast vol", "Ratio"], "rows": rows},
    }
