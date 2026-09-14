"""Morning desk, deterministic half (CLAUDE.md §6 /desk).

  python -m src.desk [--date YYYY-MM-DD]

Exit codes: 0 report printed, 2 refused (wrap missing / report needed),
1 market data failure.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date as _date, timedelta

from src import journal
from src.analyst import analyse
from src.events import fresh_flag, in_window
from src.guardian import can_trade_today
from src.market_data import MarketDataError, get_market
from src.state import Paths, DEFAULT, load_json, load_last_wrap, roll_day, save_json
from src.sync import SyncError, pull


def last_lessons(paths: Paths, n: int = 5) -> list[str]:
    if not paths.lessons.exists():
        return []
    heads = [l[3:].strip() for l in paths.lessons.read_text(encoding="utf-8").splitlines() if l.startswith("## ")]
    return heads[-n:]


def wrap_is_current(last_wrap_date: str | None, today: str, journal_empty: bool) -> tuple[bool, str]:
    """/desk needs yesterday's wrap (or today's, if re-run). A fresh install with
    an empty journal and no wrap ever is allowed once."""
    yesterday = (_date.fromisoformat(today) - timedelta(days=1)).isoformat()
    if last_wrap_date in (yesterday, today):
        return True, ""
    if last_wrap_date is None and journal_empty:
        return True, "first run: no wrap yet and journal empty"
    return False, f"Run /wrap for {yesterday} first." if last_wrap_date is None else f"Run /wrap for {yesterday} first (last wrap was {last_wrap_date})."


def breached(t: dict, price: float) -> str | None:
    long = t["direction"] == "long"
    if (price <= t["stop"]) if long else (price >= t["stop"]):
        return "stop"
    if (price >= t["target"]) if long else (price <= t["target"]):
        return "target"
    return None


def verdict(pre_ok: bool, events_flag: str | None, reads: dict) -> str:
    if not pre_ok or events_flag == "no-trade":
        return "NO-TRADE DAY"
    if any(r["strategy"] for r in reads.values()):
        return "TRADE"
    return "WAIT"


def desk(today: str, paths: Paths = DEFAULT, market_getter=get_market, out=sys.stdout, sync: bool = True) -> int:
    if sync:
        try:
            status = pull(paths.root)
        except SyncError as exc:
            print(f"SYNC FAILED: {exc}. Stopping — the record may be stale.", file=out)
            return 1
        if status != "sync off":
            print(f"record: {status}", file=out)
    settings = load_json(paths.settings)
    tickets = journal.list_tickets(journal_dir=paths.journal)
    ok, why = wrap_is_current(load_last_wrap(paths.last_wrap).get("date"), today, not tickets)
    if not ok:
        print(why, file=out)
        return 2

    acct = roll_day(load_json(paths.account_state), today)
    save_json(paths.account_state, acct)
    open_tickets = [t for t in tickets if t["status"] == "open"]
    open_pos = load_json(paths.open_positions)

    pairs = sorted({t["pair"] for t in open_tickets} | set(settings["instruments"]))
    market = {}
    for pair in pairs:
        try:
            market[pair] = market_getter(pair)
        except MarketDataError as exc:
            print(f"MARKET DATA FAILED for {pair}: {exc}. Stopping.", file=out)
            return 1

    for t in open_tickets:
        mark = market[t["pair"]].funding.get("mark_price") or float(market[t["pair"]].daily["close"].iloc[-1])
        hit = breached(t, mark)
        if hit:
            print(f"REPORT NEEDED: {t['id']} is open and mark {mark} is beyond its {hit} ({t[hit]}). Run /report first.", file=out)
            return 2

    events_flag, events = fresh_flag(today, paths.events)
    reads = {p: analyse(m.daily, m.weekly) for p, m in market.items()}
    pre = can_trade_today(acct, open_pos, settings)
    remaining = acct["daily_loss_cap"] + acct.get("realized_pnl_today", 0)

    lines = [f"MORNING REPORT  {today}",
             f"account   : balance {acct['current_balance']:.2f} · drawdown room {acct['drawdown_room']:.2f} · "
             f"daily budget left {remaining:.2f} · losses today {acct['losses_today']} · consecutive {acct['consecutive_losses']}"]
    if not pre.allow:
        lines.append(f"guardian  : NO NEW TRADES — {'; '.join(pre.reasons)}")
    lines.append("open      : " + ("; ".join(
        f"{t['id']} @ {t['fill_price']} mark {market[t['pair']].funding.get('mark_price')} stop {t['stop']} target {t['target']}"
        for t in open_tickets) or "none"))
    planned = [t for t in tickets if t["status"] == "planned"]
    if planned:
        lines.append("resting   : " + "; ".join(f"{t['id']} zone {t['entry_zone']}" for t in planned))
    for p, r in reads.items():
        lv = r["daily"]["levels"]
        lines.append(f"{p:<4} daily : {r['daily']['market_class']} / weekly {r['weekly']['market_class']} · close {lv['close']:.0f} · "
                     f"50 EMA {lv['ema50']:.0f} · ATR {lv['atr14']:.0f} · swing low {lv['last_swing_low']} high {lv['last_swing_high']} · "
                     f"funding {market[p].funding['funding_rate']} → {r['strategy'] or 'no setup'}")
    if events_flag is None:
        lines.append("events    : NOT SCOUTED today — run events_scout before any /plan")
    else:
        ev = in_window(events, today)
        lines.append(f"events    : {events_flag}" + (" — " + "; ".join(f"{e['date']} {e['name']} ({e['severity']})" for e in ev) if ev else " — none in window"))
    lessons = last_lessons(paths)
    if lessons:
        lines.append("reviewer  : " + " | ".join(lessons[-3:]))
    lines.append(f"VERDICT   : {verdict(pre.allow, events_flag, reads)}")
    print("\n".join(lines[:25]), file=out)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Morning desk report.")
    ap.add_argument("--date", default=_date.today().isoformat())
    ap.add_argument("--no-sync", action="store_true", help="do not pull the record from origin/main first")
    args = ap.parse_args(argv)
    return desk(args.date, sync=not args.no_sync)


if __name__ == "__main__":
    sys.exit(main())
