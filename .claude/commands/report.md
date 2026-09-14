After-trade intake for a closed trade. Follow CLAUDE.md §6 `/report`. Minimum typing.

1. Find the ticket: `python -m src.report pending` lists planned/open tickets.
   If several, ask which one. If none, say so and stop.
2. Ask for a **screenshot of the closed trade from Kraken Pro trade history**.
   From it, read: `fill_price`, `exit_price`, `position_qty`, `result_usd`
   (realised P&L including fees, signed), `opened_at`, `closed_at`
   (ISO `YYYY-MM-DDTHH:MM`, the exchange's timezone unless stated).
   Show the six parsed values in a short table and ask the human to confirm or
   correct. If there is no screenshot, ask for each field, one line each.
   Never take these numbers from a spreadsheet or from memory.
3. Ask only the three human fields, one message:
   - `followed_plan` yes/no (if no → `deviation_note`, one line)
   - `mid_trade_events` (or "none")
   - `emotion_note` (a few words)
4. Optionally accept a daily chart screenshot; keep it for the reviewer.
5. Close the ticket:
   ```
   python -m src.report close <id> --fill-price X --exit-price Y --qty Q --result R \
     --opened-at T --closed-at T --followed-plan yes|no [--deviation-note ".."] \
     --mid-trade-events ".." --emotion-note ".."
   ```
   The script derives `outcome` from the exit price vs stop/target and refuses
   numbers that contradict each other. If it prints `REPORT REFUSED`, show the
   reason and re-check the values with the human; use `--force` only after they
   confirm the numbers are right.
6. Show the closed ticket JSON, then run the reviewer
   (`.claude/agents/reviewer.md`, Phase 4). Until the reviewer exists, say
   "reviewer: not built yet (Phase 4)".

If the trade never filled: `python -m src.report cancel <id> --note ".."`.
If it filled and is still open: `python -m src.report open <id> --fill-price X --opened-at T`.
