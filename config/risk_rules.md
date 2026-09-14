# Risk rules — hard constraints

Every agent reads this file before acting. These rules are never relaxed,
"improved", or reinterpreted by an agent. Only the human edits this file.
Deterministic enforcement lives in `src/guardian.py`; this file is the
human-readable source of truth it implements.

1. **Max daily loss: 3% of starting balance** (Kraken Prop limit).
   The studio treats **2%** as the hard internal cap (`daily_loss_cap`).
2. **Max drawdown does not reset.** `drawdown_room` is tracked continuously
   and only ever shrinks unless the balance recovers above the floor.
3. **Risk per trade: 0.5% of starting balance.** Configurable, capped at **1%**.
4. **Instruments: BTC and ETH only.** Anything else is rejected.
5. **One open position at a time.**
6. **After two losses in a day, no new trades that day.**
7. **Every trade plan includes stop loss and take profit before entry.**
8. **Minimum reward-to-risk: 2:1.**
9. **Stops are never widened after entry.** Tightening is allowed.
10. **No new trade if a major scheduled event falls inside the expected hold
    window** (default 5 trading days) unless the human overrides explicitly.
11. **Any agent output that would breach a rule is blocked, not warned about.**

Reminder: the human places every order. Nothing in this repo sends orders.
