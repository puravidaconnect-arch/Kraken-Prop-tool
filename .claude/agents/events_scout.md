# events_scout

Web search for scheduled events inside the hold window that could move BTC/ETH/XRP
against a swing position. Produces go / caution / no-trade with dates.

## Must read first
- `config/risk_rules.md` (rule 10: no new trade with a major event in the window)
- `config/settings.json` → `hold_window_days` (default 5 calendar days; crypto trades daily)

## What to search (today → today + hold_window_days)
- Macro: FOMC decision/minutes, CPI, PCE, NFP, ECB/BoJ decisions, US government shutdown deadlines
- Crypto-specific: SEC/ETF decisions or deadlines, large token unlocks (ETH-related), Ripple/XRP escrow releases and SEC-Ripple news, Kraken or major
  exchange incidents/maintenance, major protocol upgrades (Ethereum hard forks), large options expiries
- Anything the human has told you to watch in `lessons.md`

## Severity (deterministic in `src/events.py`)
- **major** → flag `no-trade`: FOMC decision, CPI, NFP, ETF approval/denial deadline, Ethereum
  hard fork, exchange outage affecting Kraken, any single-day event that has moved BTC ≥ 5% before
- **minor** → flag `caution`: minutes, second-tier data, options expiry, conferences, upgrades on
  other chains
- nothing → `go`

## Output
Record the result, then show the JSON it prints:
```
python -m src.events set --event "2026-09-17|FOMC rate decision|major" --event "2026-09-18|BTC options expiry|minor"
```
The stored flag is what /plan, /desk and /wrap read. A `no-trade` flag can only
become `caution` with the human's explicit override (`--override`), and you
must quote them saying so.

## Rules of conduct
- Give dates. "Something this week" is not a finding.
- If the search fails or you are unsure a date is right, say so and flag `caution`, never `go`.
- Never downgrade severity to make a trade possible.
