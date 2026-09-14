Build a trade ticket for $ARGUMENTS (BTC or ETH). Follow CLAUDE.md §6 exactly.

Steps:
1. Read `config/risk_rules.md`.
2. Guardian pre-check, market data, analyst, planner, guardian verdict are all
   inside one deterministic script. Run it:
   ```
   python -m src.plan $ARGUMENTS --events-flag <flag>
   ```
   `<flag>` comes from events_scout (Phase 3). Until events_scout exists, do a
   quick web search for scheduled macro events (FOMC, CPI, ETF decisions,
   large unlocks, exchange news) inside the next `hold_window_days` trading
   days. Pass `no-trade` if a major one falls in the window, `caution` if
   minor, else `go`. Say in one line what you found and which flag you passed.
3. If the script prints `NO TRADE`, `BLOCKED`, or `MARKET DATA FAILED`, repeat
   that one line to the human and stop. Do not retry with different inputs,
   do not build a ticket by hand.
4. If it prints a ticket, show the readable block and the JSON as printed.
   Add at most 5 lines of analyst/planner judgment (nearest level, event
   context). Confirm it was saved as `status: planned` in `journal/`.
5. Checklist (order parameters for Kraken Pro) arrives in Phase 3; until then,
   remind the human to enter stop and target with the order.

Never place, simulate, or suggest placing an order. The human places every order.
