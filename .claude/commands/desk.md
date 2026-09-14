Morning desk. Follow CLAUDE.md §6 `/desk`. You are the coordinator; read
`.claude/agents/coordinator.md` first.

1. Run events_scout for today's hold window and record it:
   `python -m src.events set --event "…" …` (no events → `python -m src.events set`).
2. Run the desk:
   ```
   python -m src.desk
   ```
   - If it prints `SYNC FAILED` → the record could not be pulled from GitHub. Say so and stop;
     do not trade on a stale journal.
   - If it prints `Run /wrap for <date> first.` → say exactly that and stop.
   - If it prints `REPORT NEEDED …` → run `/report` for that ticket, then re-run.
   - If it prints `MARKET DATA FAILED` → say so and stop. No report from stale data.
3. Show the MORNING REPORT as printed (≤ 25 lines). You may add at most 3 lines
   of judgment: the one level that matters most today for each pair, and
   anything in `state/next_day_brief.md` the human should not forget.
4. The verdict line is the desk's: TRADE / WAIT / NO-TRADE DAY. Do not soften
   or upgrade it. If it is TRADE, say which pair has a setup and offer `/plan`.
