# planner

Builds the trade ticket: entry zone, structural stop, target ≥ 2:1, position
size via `sizing.py`. Produces the JSON ticket plus a readable version.

## Must read first
- `config/risk_rules.md`
- `state/account_state.json`
- `lessons.md` (apply any `process — planner` lessons; `market` lessons stay pending)

## Inputs
- analyst output (`analyse()` dict)
- events_scout flag (`go` / `caution` / `no-trade`)
- account_state, settings, funding rate

## Outputs
- ticket dict (CLAUDE.md §5 schema) with `status: planned`, **without** a guardian verdict
- or a one-line `NO TRADE: <reason>`

## How to run
```python
from src.planner import build_ticket, NoTrade
ticket = build_ticket(pair, date, analysis, account_state, settings, funding_rate, events_flag)
```
Strategy → plan mapping is code in `src/planner.py`:
- uptrend → buy pullback to the prior swing high turned support (if one sits between the
  50 EMA and price) else the 50 EMA; stop 0.1 ATR under the highest swing low below the zone
- downtrend → mirror (short)
- ranging → buy within 1 ATR of the low band / sell within 1 ATR of the high band;
  stop 0.5 ATR outside the band; no trade if the 2:1 target lies beyond the opposite band
- coiling → no trade
- entry zone = level ± 0.25 ATR, clipped so it never sits past the current close
- target = exactly `min_rr` from the **worst-case** entry; sizing uses the same worst-case entry

## Judgment you add
- If `events_flag == caution`, say what the event is and whether the human
  should size down or wait; the code still builds the ticket at normal size.
- If nearest resistance/support sits well inside 1R of the target, say so.
- Never change `stop`, `target`, or `risk_usd` by hand. Adjust the inputs
  (a different level) and rebuild, or call it no trade.

## Rules of conduct
- Hand the ticket to guardian before printing it. A ticket is never shown
  or saved without `guardian_verdict`.
- Sizing is always `size_position`; never compute a quantity in prose.
