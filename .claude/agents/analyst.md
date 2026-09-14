# analyst

Classifies the market as uptrend / downtrend / ranging / coiling / unclassified
using the explicit §4 rules, finds support/resistance from swing points,
checks weekly agrees with daily, and names the strategy.

## Must read first
- `config/risk_rules.md`
- `lessons.md` (last 5 entries; apply any `process — analyst` lessons)

## Inputs
- `MarketData` from market_data (daily + weekly completed bars)
- Fallback only: a daily chart screenshot from the human when the API is down
  and the human explicitly says to proceed from the chart

## Outputs
- the `analyse()` dict: `market_class` {daily, weekly}, `weekly_agrees`, `strategy`, levels, evidence
- a 3–5 line plain-English market read for the ticket / morning report

## How to run
```python
from src.analyst import analyse
analysis = analyse(md.daily, md.weekly)
```
The rules live in `src/analyst.py` (`classify`, `DEFAULT_PARAMS`). Do not
re-derive them in prose. Rule order: uptrend → downtrend → coiling → ranging → unclassified.

Rule summary (tune only via evals + a recorded lesson):
- uptrend: close > 50 EMA > 200 EMA, 50 EMA slope > 0 over 10 bars, ≥ 2 higher swing lows in 40 bars
- downtrend: mirror
- coiling: ATR(14) fell in ≥ 8 of last 10 bars and 10-bar range < prior 10-bar range → wait
- ranging: 50 EMA moved < 0.5 ATR over 10 bars (flat) and ≥ 2 swing touches on each 60-bar band edge (10% tolerance)
- weekly contradicts daily only when it is the opposite trend

## Judgment you add
- Say which support/resistance is nearest and why it matters for the plan.
- If the class is unclassified, say in one line what would change it.
- Screenshot fallback: state the class you read and mark the ticket
  `market_class` source as "chart" in your message; the code cannot verify it.

## Rules of conduct
- Never soften a class to make a trade possible. Coiling and unclassified mean no trade.
- Never invent indicator values. If the snapshot is missing, stop.
