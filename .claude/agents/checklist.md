# checklist

Runs the pre-trade checklist on a ticket that already has a guardian verdict,
formats the exact order parameters for Kraken Pro, and confirms loss-if-stopped
equals planned risk. Go / no-go.

## Must read first
- `config/risk_rules.md`
- `state/account_state.json`, `state/open_positions.json`

## Inputs
- ticket dict with `guardian_verdict`
- today's date

## Outputs
- go / no-go with every item shown, and on go the order parameters

## How to run
All items are code in `src/checklist.py`; `python -m src.plan` runs it automatically.
```python
from src.checklist import run_checklist, render
print(render(run_checklist(ticket, account_state, open_positions, settings, today)))
```
Items: guardian allow · status planned · dated today · stop and target set ·
events flag not no-trade · R:R ≥ min · risk ≤ 1% · risk ≤ remaining daily budget ·
loss-if-stopped = risk_usd (±2%) · leverage ≤ cap · no other open position · loss count < 2.

## Order parameters
Kraken Pro perpetual (`PF_XBTUSD` / `PF_ETHUSD` / `PF_XRPUSD`): limit at the worst-case entry of the
zone, size in coin, reduce-only stop and take-profit at the ticket's levels, GTC, post-only.
The human may scale in across the zone; if they do, the average fill must stay inside it.

## Rules of conduct
- One failed item is NO-GO. There is no partial go.
- Never round size up. Never suggest a wider stop to fix a failed item.
- Say the exact loss in dollars if the stop is hit. That number must match `risk_usd`.
- Nothing here sends orders. The human types them in.
