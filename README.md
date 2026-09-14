# Trading Studio

A local agent studio for swing-trading BTC and ETH perpetuals on a Kraken Prop
funded account, on the daily timeframe. Its first job is to keep the account
alive; its second is to produce consistent, rule-based trade plans; its third
is to improve its own rules from a structured journal.

**The human places every order.** Nothing in this repo sends orders to an
exchange. It only reads Kraken's public price data, which needs no API key.

The full spec is `CLAUDE.md`. The hard rules are `config/risk_rules.md`.

## Two ways to run it

**On your own computer.** Clone the repo, install, open the folder in Claude Code.
Needed for the phone form and for long backtests.

```
git clone https://github.com/puravidaconnect-arch/Kraken-Prop-tool
cd Kraken-Prop-tool
pip install -r requirements.txt
pytest
```

**In Claude Code on the web.** Nothing to install. Start a session on this repo,
and in the environment's network settings allow `api.kraken.com` and
`futures.kraken.com`. Each session is a fresh copy of the repo, so the record
(state, journal, daily logs, lessons) lives on GitHub: `/desk` pulls it first,
and `/plan`, `/report`, the reviewer and `/wrap` push it after every write.
Always finish a trading day with `/wrap`; if it prints `SYNC FAILED`, run
`python -m src.sync push` until it succeeds before closing the session. The
push lands on `main` only when the session changed nothing but the record; a
session that also edited code pushes to its own branch and says so, so do
code work and trading in separate sessions. The phone form does not apply on
the web: `/report` takes the screenshot from the Claude app instead.

## One-time setup

Then set your real numbers before the first day:

- `config/settings.json`: `starting_balance`, `leverage_cap`, `max_drawdown_pct`,
  `risk_pct` (0.5% default, capped at 1%).
- `state/account_state.json`: `starting_balance`, `current_balance`,
  `max_drawdown_floor`, `drawdown_room`, `daily_loss_cap`. The drawdown floor
  never moves, so get it right on day one.

Open the folder in Claude Code. `CLAUDE.md` loads as project instructions and
the four slash commands below become available.

## The daily loop

Every trading day runs the same four commands, in order. Each is a conversation
with the coordinator agent, which calls the deterministic scripts in `src/`.

### 1. Morning: `/desk`

Scouts scheduled events for the hold window, refreshes BTC and ETH, and prints
the morning report ending in **TRADE / WAIT / NO-TRADE DAY**. It refuses to run
if yesterday was not wrapped (first day excepted), and demands a `/report`
first if an open position is already past its stop or target.

### 2. If TRADE: `/plan BTC` or `/plan ETH`

Guardian pre-check → market data → analyst → planner → guardian verdict →
checklist. You get the ticket, the checklist, and the exact order parameters
for Kraken Pro. You place the order yourself with the stop and take-profit
attached. If it prints `NO TRADE`, `BLOCKED` or `NO-GO`, that is the answer.

When the order fills, tell the agent or run:

```
python -m src.report open <ticket-id> --fill-price X --opened-at "YYYY-MM-DDTHH:MM"
```

### 3. When the trade closes: `/report`

Paste a screenshot of the closed trade from Kraken Pro trade history. The agent
reads fill, exit, quantity, result, opened and closed times; you confirm; then
you answer three questions: followed the plan? anything mid-trade? how did you
feel? The reviewer runs immediately and tags the trade.

From your phone instead: on the computer run

```
python -m src.form --lan
```

and open the printed URL with the printed PIN. It writes the same journal JSON.

### 4. End of day: `/wrap` (or say "wrap it up")

Confirms any open or resting tickets, reviews anything unreviewed, updates
`state/account_state.json`, rewrites `state/open_positions.json`, writes
`daily_log/YYYY-MM-DD.md` and `state/next_day_brief.md`, exports
`journal/journal.csv` (a view only, never read back), and stamps
`state/last_wrap.json`.

Days with no trade still need `/desk` and `/wrap`. The wrap unlocks the next
morning.

## Every few weeks

- `python -m src.lessons pending` lists market lessons waiting on evidence. They
  become rules only after 20 closed trades **and** a winning backtest.
- Build real eval windows once, label them by hand, and score the analyst:

  ```
  python -m src.market_data download BTC --out evals/history/BTC_daily.csv
  python evals/make_windows.py evals/history/BTC_daily.csv --pair BTC --auto 20
  # fill in every TODO in evals/labels.json from the chart, then
  python evals/run_evals.py
  ```

  The 20 shipped `synth_*` windows are synthetic and only prove the pipeline runs.
- Backtest a candidate rule over two or more years of daily data (Kraken's
  historical OHLCVT CSV export loads as-is):

  ```
  python -m src.backtest evals/history/BTC_daily.csv --set min_stop_atr=1.0
  ```

- Read `lessons.md` and open `journal/journal.csv` in a spreadsheet. The JSON
  files in `journal/` are the single source of truth.

## Where things live

| Path | What |
|---|---|
| `config/` | `settings.json` (numbers), `risk_rules.md` (hard rules, human-edited only) |
| `state/` | live account state, open positions, events, next-day brief, last wrap |
| `journal/` | one JSON per trade, plus the CSV view |
| `daily_log/` | one short markdown file per wrapped day |
| `lessons.md` | the growing rulebook |
| `src/` | all deterministic logic, each module runnable with `python -m src.<name>` |
| `.claude/agents/` | one markdown file per agent: role, inputs, outputs, rules |
| `.claude/commands/` | `/desk`, `/plan`, `/report`, `/wrap` |
| `evals/` | labelled windows and the scorer |
| `tests/` | `pytest` |

## Three rules for the human

- Never edit `state/` or `journal/` files by hand. The scripts own them.
- Only you edit `config/risk_rules.md`. No agent will, ever.
- When the guardian blocks, it is doing its first job. The way to change its
  mind is a lesson and a backtest, not a tweak.
