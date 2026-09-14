# Trading Studio — Build Spec

Read this whole file before writing any code. Build **one phase at a time**, run its acceptance checks, and stop for my review before starting the next phase. If anything is ambiguous, ask before assuming.

Copy this file to `CLAUDE.md` in the repo root so it is loaded in every session.

---

## 1. Purpose

A local agent studio that helps me swing-trade BTC and ETH perpetuals on a **Kraken Prop** funded account, on the daily timeframe. The studio's first job is to keep the account alive; its second job is to produce consistent, rule-based trade plans; its third job is to improve its own rules from a structured journal.

**The human places every order.** Nothing in this repo sends orders to an exchange. Automated execution is out of scope unless I explicitly add it later.

---

## 2. Hard constraints (never violate, never "improve")

These are in `config/risk_rules.md` and every agent must read that file before acting.

- Max daily loss: **3% of starting balance**. Studio treats **2%** as the hard internal cap.
- Max drawdown does not reset. Track `drawdown_room` continuously.
- Risk per trade: **0.5% of starting balance**, configurable but capped at 1%.
- Instruments: **BTC and ETH only**. Reject anything else.
- One open position at a time.
- After **two losses in a day**, no new trades that day.
- Every trade plan must include stop loss and take profit **before** entry.
- Minimum reward-to-risk: **2:1**.
- Stops are never widened after entry. Tightening is allowed.
- No new trade if a major scheduled event falls inside the expected hold window (default 5 trading days) unless I override explicitly.
- Any agent output that would breach a rule must be **blocked**, not warned about.

---

## 3. Repo layout

```
trading-studio/
├── CLAUDE.md                  # this spec
├── config/
│   ├── risk_rules.md          # section 2 above, human-readable
│   └── settings.json          # starting_balance, risk_pct, instruments, hold_window_days
├── state/
│   ├── account_state.json     # live numbers (schema in §5)
│   ├── open_positions.json
│   ├── next_day_brief.md
│   └── last_wrap.json         # {"date": "YYYY-MM-DD"}
├── journal/                   # one file per trade: YYYY-MM-DD_BTC_long.json
├── daily_log/                 # YYYY-MM-DD.md
├── lessons.md                 # the growing rulebook (schema in §7)
├── evals/
│   ├── charts/                # historical OHLCV snapshots with known outcomes
│   └── run_evals.py
├── src/
│   ├── market_data.py         # Kraken public API → OHLCV + indicators
│   ├── indicators.py          # EMA, RSI, ATR, swing highs/lows
│   ├── sizing.py              # position size formula
│   ├── guardian.py            # rule checks, pure functions, no LLM
│   ├── backtest.py
│   └── journal.py             # read/write/summarise journal
├── .claude/
│   ├── commands/
│   │   ├── desk.md
│   │   ├── wrap.md
│   │   ├── plan.md            # /plan BTC → full trade ticket
│   │   └── report.md          # /report → after-trade report intake
│   └── agents/                # one .md per agent (§4)
└── tests/
```

Python 3.11+, `pandas`, `requests`, `pytest`. No other heavy dependencies without asking.

---

## 4. Agents

Each agent is a markdown file in `.claude/agents/` describing its role, inputs, outputs, and the rules it must read. Deterministic logic (math, rule checks, data fetching) lives in `src/` as plain Python and is **called by** agents, not reimplemented in prose.

| Agent | Responsibility | Reads | Writes |
|---|---|---|---|
| **guardian** | Gatekeeper. Validates every plan against `risk_rules.md` and `account_state.json`. Blocks violations. | risk_rules, account_state, open_positions | verdict: allow / block + reason |
| **market_data** | Pulls daily + weekly OHLCV for BTC/ETH from Kraken public API, computes indicators, reads funding rate. | settings | structured snapshot (JSON) |
| **analyst** | Classifies market as trending / ranging / coiling using explicit rules. Finds support/resistance from swing points. Checks weekly agrees with daily. Picks strategy. Accepts a chart screenshot as fallback input. | snapshot, lessons | market read + strategy choice |
| **events_scout** | Web search for scheduled macro events, ETF decisions, large token unlocks, exchange news within hold window. | settings | flag: go / caution / no-trade, with dates |
| **planner** | Builds the trade ticket: entry zone, structural stop, target ≥ 2:1, position size via `sizing.py`. | analyst output, events flag, account_state | trade ticket (JSON + readable) |
| **checklist** | Runs the pre-trade checklist, formats exact order parameters for Kraken Pro, confirms loss-if-stopped equals planned risk. | ticket, guardian verdict | go / no-go + order params |
| **reviewer** | After each closed trade: compares plan to outcome, tags it, writes a one-paragraph lesson. Separates process errors from market noise. | journal entry, lessons | journal tag + lessons.md append |
| **coordinator** | Orchestrates the flow for `/plan`, `/desk`, `/wrap`. Handles "no trade today" cleanly. | all state | — |

### Analyst classification rules (starting point — tune later via evals)

- **Uptrend**: close > 50 EMA, 50 EMA > 200 EMA, 50 EMA slope positive over 10 bars, at least two higher swing lows in last 40 bars.
- **Downtrend**: mirror.
- **Ranging**: price has touched both a defined high band and low band ≥ 2 times each in last 60 bars; 50 EMA slope ~flat.
- **Coiling**: ATR(14) declining for ≥ 10 bars and range contracting; treat as "wait for breakout".
- Weekly must not contradict daily for a trade to be allowed.

### Strategy → plan mapping

- Uptrend → buy pullback to 50 EMA or prior swing high turned support; stop below last swing low.
- Downtrend → mirror (short).
- Ranging → buy near low band / sell near high band; stop just outside band.
- Coiling → no trade until daily close outside the range; then treat as trend.

---

## 5. Data contracts

### `state/account_state.json`
```json
{
  "starting_balance": 5000,
  "current_balance": 5000,
  "max_drawdown_floor": 4500,
  "drawdown_room": 500,
  "daily_loss_cap": 100,
  "losses_today": 0,
  "trades_today": 0,
  "consecutive_losses": 0,
  "as_of": "2026-09-14"
}
```

### Trade ticket (`journal/*.json`)
```json
{
  "id": "2026-09-14_BTC_long",
  "pair": "BTC", "direction": "long",
  "strategy": "trend_pullback",
  "market_class": {"daily": "uptrend", "weekly": "uptrend"},
  "entry_zone": [99500, 100500],
  "stop": 94000, "target": 112000,
  "stop_distance_pct": 6.0, "stop_distance_atr": 1.8,
  "rr": 2.0,
  "risk_usd": 25, "position_usd": 417, "position_qty": 0.00417,
  "leverage_effective": 0.08,
  "funding_rate": 0.0001,
  "events_flag": "go",
  "guardian_verdict": "allow",
  "status": "planned | open | closed",
  "opened_at": null, "closed_at": null,
  "fill_price": null, "exit_price": null,
  "outcome": null,
  "result_usd": null,
  "followed_plan": null,
  "deviation_note": null,
  "mid_trade_events": null,
  "emotion_note": null,
  "review_tag": null,
  "lesson": null
}
```

`outcome` ∈ `stop_hit | target_hit | exited_early | exited_late | cancelled`
`review_tag` ∈ `good_trade_bad_outcome | bad_trade_good_outcome | good_trade_good_outcome | bad_trade_bad_outcome | rule_broken | stop_too_tight | entry_chased`

### Position sizing (`src/sizing.py`)
```
risk_usd      = starting_balance * risk_pct
stop_dist_pct = abs(entry - stop) / entry
position_usd  = risk_usd / stop_dist_pct
position_qty  = position_usd / entry
```
Must raise if `stop_dist_pct == 0` or if `position_usd * leverage` implied > account leverage cap.

---

## 6. Slash commands

### `/plan <BTC|ETH>`
1. guardian pre-check (can I trade today at all?)
2. market_data → analyst → events_scout → planner → guardian → checklist
3. Print the ticket in readable form + the JSON. Save as `status: planned`.
4. If any step returns block / no-trade, say so in one line and stop.

### `/report`
After-trade intake, designed for minimum typing:
1. Ask for a **screenshot of the closed trade from Kraken Pro trade history**. Parse `fill_price`, `exit_price`, `position_qty`, `result_usd`, `opened_at`, `closed_at`. Show the parsed values and ask me to confirm or correct. If no screenshot, fall back to asking each field.
2. Ask only the three human fields: `followed_plan` (+ `deviation_note` if no), `mid_trade_events`, `emotion_note`.
3. Optionally accept a daily chart screenshot for the reviewer.
4. Mark ticket `closed`, then run **reviewer** immediately.
The JSON journal is the single source of truth. Never take trade data from a spreadsheet.

### `/wrap`  (also triggered by "wrap it up")
1. Find open/planned tickets missing reports → run `/report` for each.
2. Run reviewer on every trade closed today (if not already).
3. Update `account_state.json` (balance, drawdown_room, losses_today, consecutive_losses).
4. Rewrite `open_positions.json`.
5. Write `daily_log/YYYY-MM-DD.md` (≤ 15 lines).
6. Write `state/next_day_brief.md`: open positions + levels to watch, events in window, rules flagged by reviewer, one-line market posture.
7. Export the full journal to `journal/journal.csv` (one row per trade, flat columns) so I can open it in a spreadsheet. The CSV is a **view only** — never read from it.
8. Write `last_wrap.json`.

### `/desk`
1. If `last_wrap.date` is not the previous trading day → stop and say "Run /wrap for <date> first."
2. If any ticket is `open` and price is beyond its stop/target → ask for `/report` before continuing.
3. Load state + brief + last 5 lessons.
4. market_data refresh for BTC and ETH; events_scout for hold window.
5. Print the **morning report** (≤ 25 lines): account status & remaining daily budget, open trades vs stop/target, market read for BTC & ETH, events, reviewer reminders, verdict: **TRADE / WAIT / NO-TRADE DAY**.

---

## 7. Learning layer

### `lessons.md` format
```
## 2026-09-20 — process — analyst
Called uptrend with flat 200 EMA. Add slope check. [applied: yes, analyst.md §rules]

## 2026-09-22 — market — planner
Stop at 1.5×ATR hit by wick twice this month. Candidate: 2×ATR. [status: pending backtest, n=6]
```

Rules:
- **process** lessons → apply immediately by editing the relevant agent file. Record where.
- **market** lessons → `pending` until n ≥ 20 trades AND `backtest.py` shows improvement over ≥ 2 years of daily data. Only then edit rules.
- Reviewer never edits `risk_rules.md`. Only I do.
- Any rule edit → run `evals/run_evals.py` and paste the before/after summary in the lesson entry.

### `evals/`
- Store ≥ 20 historical daily windows (CSV) with a hand-labelled `expected_class` and `expected_outcome`.
- `run_evals.py` runs the analyst classification + planner on each and reports agreement %.

---

## 8. Build phases & acceptance

### Phase 1 — Skeleton & safety (build first)
- Repo layout, `settings.json`, `risk_rules.md`, `account_state.json`.
- `sizing.py`, `guardian.py` as pure functions with `pytest` coverage.
- `journal.py` read/write.
- **Accept when:** tests pass; guardian correctly blocks: altcoin, >1% risk, 3rd trade after 2 losses, missing stop, R:R < 2, second concurrent position.

### Phase 2 — Data & analysis
- `market_data.py` (Kraken public OHLC endpoint, daily + weekly), `indicators.py`.
- analyst.md, planner.md, `/plan`.
- **Accept when:** `/plan BTC` prints a full ticket from live data with correct sizing, or a clean "no trade" with reason.

### Phase 3 — Daily loop
- events_scout.md, checklist.md, `/report`, `/wrap`, `/desk`, coordinator.md.
- **Accept when:** I can run `/plan` → `/report` → `/wrap` → (new session) `/desk` end-to-end on a simulated trade; `/report` correctly parses a Kraken Pro trade-history screenshot; `/wrap` writes `journal.csv`; and `/desk` refuses to run without a prior `/wrap`.

### Phase 4 — Learning layer
- reviewer.md, `lessons.md`, `backtest.py`, `evals/`.
- **Accept when:** a closed trade produces a tagged journal entry and a lesson; a market lesson stays pending until n ≥ 20; evals run and report a score.

### Phase 5 — Trade-input tool (DEFERRED — do not build until I ask)
Decision made 2026-09-14: Phase 1-4 use `/report` with screenshot parsing plus the CSV export. The dedicated input tool is deferred.
When Phase 4 is accepted, **remind me** that this phase is next and ask which option I want:
- (a) Check whether Kraken Pro / Breakout terminal exports trade history as CSV; if yes, add `journal.py` ingest so `/report` only needs the three human fields.
- (b) A one-page local form (Streamlit or plain HTML) that writes the same journal JSON, for phone use on the home network.
- **Accept when:** a closed trade can be journaled without touching the terminal, and the resulting JSON is identical to what `/report` produces.

---

## 9. Working agreements for Claude Code

- Prefer small, readable Python over clever abstractions. This is a personal tool.
- Deterministic things (math, rules, data) go in `src/` with tests. Judgment things go in agent prompts.
- Never fabricate market data. If the API fails, say so and stop.
- Never write a trade ticket without a guardian verdict attached.
- Keep every agent file under ~80 lines. If it grows, split it.
- After each phase, give me a 5-line summary: what was built, how to run it, what you assumed.
