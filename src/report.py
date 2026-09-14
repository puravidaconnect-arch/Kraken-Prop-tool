"""After-trade intake, deterministic half. The agent parses the screenshot
and confirms values with the human; this writes them to the journal.

  python -m src.report open   ID --fill-price X --opened-at T
  python -m src.report close  ID --fill-price X --exit-price Y --qty Q --result R
                                 --opened-at T --closed-at T --followed-plan yes|no
                                 [--deviation-note ..] --mid-trade-events .. --emotion-note ..
  python -m src.report cancel ID [--note ..]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from src import journal
from src.state import DEFAULT
from src.sync import SyncError, push

LEVEL_TOL = 0.003  # exit within 0.3% of stop/target counts as that level


def derive_outcome(t: dict, exit_price: float) -> str:
    """stop_hit / target_hit / exited_early / exited_late from the exit price."""
    long = t["direction"] == "long"
    stop, target = t["stop"], t["target"]
    near = lambda level: abs(exit_price - level) <= level * LEVEL_TOL
    if near(stop) or (exit_price < stop if long else exit_price > stop):
        return "stop_hit"
    if near(target):
        return "target_hit"
    if exit_price > target if long else exit_price < target:
        return "exited_late"
    return "exited_early"


def check_consistency(t: dict, fill: float, exit_: float, qty: float, result: float) -> list[str]:
    """Sanity checks on the reported numbers. Returns problems; empty = fine."""
    problems = []
    long = t["direction"] == "long"
    gross = (exit_ - fill) * qty * (1 if long else -1)
    if gross != 0 and result != 0 and (gross > 0) != (result > 0):
        problems.append(f"result_usd {result} has the opposite sign to price move ({gross:+.2f} gross)")
    if abs(result - gross) > max(abs(gross) * 0.25, 5.0):
        problems.append(f"result_usd {result} is far from gross {gross:+.2f} (fees/funding cannot explain it)")
    if t.get("position_qty") and abs(qty - t["position_qty"]) > t["position_qty"] * 0.25:
        problems.append(f"qty {qty} differs from planned {t['position_qty']} by more than 25%")
    return problems


def mark_open(ticket_id: str, fill_price: float, opened_at: str, journal_dir: Path = None) -> dict:
    jd = journal_dir or journal.JOURNAL_DIR
    t = journal.load_ticket(ticket_id, jd)
    if t["status"] != "planned":
        raise ValueError(f"{ticket_id} is {t['status']}, only a planned ticket can be opened")
    return journal.update_ticket(ticket_id, jd, status="open", fill_price=fill_price, opened_at=opened_at)


def close_ticket(ticket_id: str, *, fill_price: float, exit_price: float, position_qty: float,
                 result_usd: float, opened_at: str, closed_at: str, followed_plan: bool,
                 deviation_note: str | None, mid_trade_events: str | None, emotion_note: str | None,
                 outcome: str | None = None, force: bool = False, journal_dir: Path = None) -> dict:
    jd = journal_dir or journal.JOURNAL_DIR
    t = journal.load_ticket(ticket_id, jd)
    if t["status"] not in ("planned", "open"):
        raise ValueError(f"{ticket_id} is already {t['status']}")
    if not followed_plan and not deviation_note:
        raise ValueError("followed_plan is no: deviation_note is required")
    problems = check_consistency(t, fill_price, exit_price, position_qty, result_usd)
    if problems and not force:
        raise ValueError("reported numbers look wrong (use --force if they are right): " + "; ".join(problems))
    outcome = outcome or derive_outcome(t, exit_price)
    return journal.update_ticket(
        ticket_id, jd, status="closed", fill_price=fill_price, exit_price=exit_price,
        position_qty=position_qty, result_usd=result_usd, opened_at=opened_at, closed_at=closed_at,
        outcome=outcome, followed_plan=followed_plan, deviation_note=deviation_note,
        mid_trade_events=mid_trade_events, emotion_note=emotion_note,
    )


def cancel_ticket(ticket_id: str, note: str | None = None, journal_dir: Path = None) -> dict:
    jd = journal_dir or journal.JOURNAL_DIR
    t = journal.load_ticket(ticket_id, jd)
    if t["status"] != "planned":
        raise ValueError(f"only a planned ticket can be cancelled, {ticket_id} is {t['status']}")
    return journal.update_ticket(ticket_id, jd, status="cancelled", outcome="cancelled", deviation_note=note)


def pending_reports(journal_dir: Path = None) -> list[dict]:
    """Tickets that are planned or open: /wrap must confirm each one with the human."""
    jd = journal_dir or journal.JOURNAL_DIR
    return [t for t in journal.list_tickets(journal_dir=jd) if t["status"] in ("planned", "open")]


def _yes_no(v: str) -> bool:
    if v.lower() in ("yes", "y", "true", "1"):
        return True
    if v.lower() in ("no", "n", "false", "0"):
        return False
    raise argparse.ArgumentTypeError("expected yes or no")


def _push(message: str) -> int:
    try:
        status = push(message)
    except SyncError as exc:
        print(f"SYNC FAILED: {exc}. Saved locally only; run python -m src.sync push before closing.")
        return 1
    if status != "sync off":
        print(f"record: {status}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Write a trade report to the journal.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    o = sub.add_parser("open"); o.add_argument("id"); o.add_argument("--fill-price", type=float, required=True); o.add_argument("--opened-at", required=True)
    c = sub.add_parser("close"); c.add_argument("id")
    for name in ("--fill-price", "--exit-price", "--qty", "--result"):
        c.add_argument(name, type=float, required=True)
    c.add_argument("--opened-at", required=True); c.add_argument("--closed-at", required=True)
    c.add_argument("--followed-plan", type=_yes_no, required=True); c.add_argument("--deviation-note")
    c.add_argument("--mid-trade-events", default=None); c.add_argument("--emotion-note", default=None)
    c.add_argument("--outcome", choices=journal.OUTCOMES); c.add_argument("--force", action="store_true")
    x = sub.add_parser("cancel"); x.add_argument("id"); x.add_argument("--note")
    p = sub.add_parser("pending")
    args = ap.parse_args(argv)
    try:
        if args.cmd == "open":
            t = mark_open(args.id, args.fill_price, args.opened_at)
        elif args.cmd == "close":
            t = close_ticket(args.id, fill_price=args.fill_price, exit_price=args.exit_price, position_qty=args.qty,
                             result_usd=args.result, opened_at=args.opened_at, closed_at=args.closed_at,
                             followed_plan=args.followed_plan, deviation_note=args.deviation_note,
                             mid_trade_events=args.mid_trade_events, emotion_note=args.emotion_note,
                             outcome=args.outcome, force=args.force)
        elif args.cmd == "cancel":
            t = cancel_ticket(args.id, args.note)
        else:
            for t in pending_reports():
                print(f"{t['id']}  {t['status']}  fill {t.get('fill_price')}  stop {t['stop']}  target {t['target']}")
            return 0
    except (ValueError, FileNotFoundError) as exc:
        print(f"REPORT REFUSED: {exc}")
        return 2
    print(json.dumps(t, indent=2))
    return _push(f"report {args.id}")


if __name__ == "__main__":
    sys.exit(main())
