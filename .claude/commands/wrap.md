End-of-day wrap. Also triggered by "wrap it up". Follow CLAUDE.md §6 `/wrap`.
You are the coordinator; read `.claude/agents/coordinator.md` first.

1. `python -m src.report pending`. For every planned or open ticket ask the
   human, in one message, which applies:
   - still resting / still open (carry it forward, nothing to do)
   - filled and still open → `python -m src.report open ...`
   - closed → run `/report` for it now
   - never filled and abandoned → `python -m src.report cancel ...`
2. `python -m src.review unreviewed`. For every trade listed, run the reviewer
   (`.claude/agents/reviewer.md`) before wrapping.
3. Ask the human for a one-line market posture for tomorrow (or write one
   from today's market reads if they say "you write it"). Then:
   ```
   python -m src.wrap --date YYYY-MM-DD --posture "…"
   ```
   This updates `state/account_state.json`, rewrites `state/open_positions.json`,
   writes `daily_log/YYYY-MM-DD.md` (≤ 15 lines) and `state/next_day_brief.md`,
   exports `journal/journal.csv` (view only, never read it), and writes
   `state/last_wrap.json`.
4. Show the WRAPPED summary line and the brief. If it lists UNREVIEWED trades,
   say so. Stop.

Never edit the state files by hand. Never read `journal.csv`.
