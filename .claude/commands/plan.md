Build a trade ticket for $ARGUMENTS (BTC, ETH or XRP). Follow CLAUDE.md §6 exactly.
You are the coordinator; read `.claude/agents/coordinator.md` first.

1. Read `config/risk_rules.md`.
2. Run events_scout (`.claude/agents/events_scout.md`): web search, then record
   the result with `python -m src.events set --event "YYYY-MM-DD|name|major|minor" ...`.
   Say in one line what you found and the flag it produced. If the flag is
   `no-trade`, stop here unless the human explicitly overrides
   (`--override`, recorded in the file).
3. Run the pipeline (guardian pre-check → market data → analyst → planner →
   guardian → checklist):
   ```
   python -m src.plan $ARGUMENTS
   ```
4. If it prints `NO TRADE`, `BLOCKED`, `NO-GO` or `MARKET DATA FAILED`, repeat that
   one line to the human and stop. Do not retry with different inputs, do
   not build a ticket by hand, do not edit state.
5. If it prints a ticket, show the readable block, the checklist with order
   parameters, and the JSON as printed. Add at most 5 lines of analyst /
   planner judgment (nearest level, event context, funding). Confirm it was
   saved as `status: planned` in `journal/`.
6. Remind the human: when the order fills, run
   `python -m src.report open <id> --fill-price X --opened-at "YYYY-MM-DDTHH:MM"`
   or tell you and you will run it.

Never place, simulate, or suggest placing an order. The human places every order.
