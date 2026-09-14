"""End-of-day wrap, deterministic half (CLAUDE.md §6 /wrap steps 3–8).
Steps 1–2 (confirm pending tickets, run reviewer) happen in the agent
conversation before this runs.

  python -m src.wrap --date YYYY-MM-DD [--posture "one line"]
"""
from __future__ import annotations

import argparse
import sys
from datetime import date as _date, timedelta
from pathlib import Path

from src import journal
from src.events import in_window, load_events
from src.state import Paths, DEFAULT, load_json, save_json, save_last_wrap
from src.sync import SyncError, push


def open_position_row(t: dict) -> dict:
    return {k: t.get(k) for k in ("id", "pair", "direction", "fill_price", "stop", "target", "position_qty", "opened_at")}


def compute_account_state(prev: dict, tickets: list[dict], date: str) -> dict:
    """Balance and counters from the journal. Drawdown floor never moves."""
    closed = [t for t in tickets if t["status"] == "closed" and t.get("result_usd") is not None]
    closed_today = [t for t in closed if (t.get("closed_at") or "")[:10] == date]
    opened_today = [t for t in tickets if (t.get("opened_at") or "")[:10] == date]
    balance = prev["starting_balance"] + sum(t["result_usd"] for t in closed)
    consecutive = 0
    for t in sorted(closed, key=lambda t: t["closed_at"], reverse=True):
        if t["result_usd"] < 0:
            consecutive += 1
        else:
            break
    return {
        **prev,
        "current_balance": round(balance, 2),
        "drawdown_room": round(balance - prev["max_drawdown_floor"], 2),
        "realized_pnl_today": round(sum(t["result_usd"] for t in closed_today), 2),
        "losses_today": sum(1 for t in closed_today if t["result_usd"] < 0),
        "trades_today": len(opened_today),
        "consecutive_losses": consecutive,
        "as_of": date,
    }


def lessons_dated(lessons_path: Path, date: str) -> list[str]:
    if not lessons_path.exists():
        return []
    return [line.strip("# ").strip() for line in lessons_path.read_text(encoding="utf-8").splitlines()
            if line.startswith("## ") and date in line]


def daily_log_text(date: str, acct: dict, closed_today: list[dict], open_pos: list[dict], planned: list[dict], posture: str) -> str:
    lines = [f"# {date}", f"balance {acct['current_balance']:.2f} · pnl today {acct['realized_pnl_today']:+.2f} · "
             f"drawdown room {acct['drawdown_room']:.2f} · losses today {acct['losses_today']} · consecutive {acct['consecutive_losses']}"]
    for t in closed_today:
        lines.append(f"closed {t['id']}: {t['outcome']} {t['result_usd']:+.2f} · followed plan {t['followed_plan']} · tag {t.get('review_tag')}")
    for p in open_pos:
        lines.append(f"open {p['id']}: fill {p['fill_price']} stop {p['stop']} target {p['target']}")
    for t in planned:
        lines.append(f"planned {t['id']}: zone {t['entry_zone']} stop {t['stop']} target {t['target']}")
    if not closed_today and not open_pos and not planned:
        lines.append("no trades")
    lines.append(f"posture: {posture}")
    return "\n".join(lines[:15]) + "\n"


def brief_text(date: str, acct: dict, open_pos: list[dict], planned: list[dict], events: list[dict],
               flagged: list[str], posture: str) -> str:
    nxt = (_date.fromisoformat(date) + timedelta(days=1)).isoformat()
    lines = [f"# Brief for {nxt}  (wrapped {date})", "",
             f"Account: balance {acct['current_balance']:.2f}, drawdown room {acct['drawdown_room']:.2f}, "
             f"daily budget {acct['daily_loss_cap']:.2f}, consecutive losses {acct['consecutive_losses']}", "",
             "## Open positions & levels"]
    lines += [f"- {p['id']}: {p['direction']} {p['position_qty']} @ {p['fill_price']} · stop {p['stop']} · target {p['target']}" for p in open_pos] or ["- none"]
    lines += ["", "## Resting plans"]
    lines += [f"- {t['id']}: zone {t['entry_zone']} · stop {t['stop']} · target {t['target']}" for t in planned] or ["- none"]
    lines += ["", "## Events in hold window"]
    lines += [f"- {e['date']} {e['name']} ({e['severity']})" for e in events] or ["- none scouted"]
    lines += ["", "## Rules flagged by reviewer"]
    lines += [f"- {f}" for f in flagged] or ["- none"]
    lines += ["", f"## Posture", posture, ""]
    return "\n".join(lines)


def wrap(date: str, posture: str = "not stated", paths: Paths = DEFAULT) -> dict:
    tickets = journal.list_tickets(journal_dir=paths.journal)
    prev = load_json(paths.account_state)
    acct = compute_account_state(prev, tickets, date)
    save_json(paths.account_state, acct)

    open_pos = [open_position_row(t) for t in tickets if t["status"] == "open"]
    save_json(paths.open_positions, open_pos)
    planned = [t for t in tickets if t["status"] == "planned"]
    closed_today = journal.tickets_closed_on(date, paths.journal)

    paths.daily_log.mkdir(exist_ok=True)
    (paths.daily_log / f"{date}.md").write_text(daily_log_text(date, acct, closed_today, open_pos, planned, posture), encoding="utf-8")

    nxt = (_date.fromisoformat(date) + timedelta(days=1)).isoformat()
    events = in_window(load_events(paths.events), nxt)
    flagged = lessons_dated(paths.lessons, date)
    paths.next_day_brief.write_text(brief_text(date, acct, open_pos, planned, events, flagged, posture), encoding="utf-8")

    csv_path = journal.export_csv(paths.journal, paths.journal / "journal.csv") if tickets else None
    save_last_wrap(date, paths.last_wrap)
    return {"date": date, "account_state": acct, "open_positions": open_pos, "planned": [t["id"] for t in planned],
            "closed_today": [t["id"] for t in closed_today], "csv": str(csv_path) if csv_path else None,
            "unreviewed": [t["id"] for t in closed_today if not t.get("review_tag")]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="End-of-day wrap.")
    ap.add_argument("--date", default=_date.today().isoformat())
    ap.add_argument("--posture", default="not stated", help="one-line market posture for the brief")
    ap.add_argument("--no-sync", action="store_true", help="do not push the record to origin/main")
    args = ap.parse_args(argv)
    r = wrap(args.date, args.posture)
    a = r["account_state"]
    print(f"WRAPPED {r['date']}: balance {a['current_balance']:.2f} · pnl today {a['realized_pnl_today']:+.2f} · "
          f"drawdown room {a['drawdown_room']:.2f} · losses today {a['losses_today']} · consecutive {a['consecutive_losses']}")
    print(f"  closed today: {r['closed_today'] or 'none'}   open: {[p['id'] for p in r['open_positions']] or 'none'}   planned: {r['planned'] or 'none'}")
    if r["unreviewed"]:
        print(f"  UNREVIEWED closed trades (run reviewer): {r['unreviewed']}")
    print(f"  wrote daily_log/{r['date']}.md, state/next_day_brief.md, {'journal/journal.csv' if r['csv'] else 'no csv (empty journal)'}, state/last_wrap.json")
    if args.no_sync:
        return 0
    try:
        status = push(f"wrap {r['date']}")
    except SyncError as exc:
        print(f"SYNC FAILED: {exc}\n  The day is NOT saved to GitHub. Fix the push (python -m src.sync push) before closing this session.")
        return 1
    if status != "sync off":
        print(f"  record: {status}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
