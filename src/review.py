"""Reviewer, deterministic half. Proposes a tag with evidence; the agent
confirms and writes the one-paragraph lesson. Records both.

  python -m src.review suggest ID
  python -m src.review record ID --tag T --kind process|market --agent A --lesson ".." [--applied "planner.md §rules"]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from src import journal
from src.lessons import Lesson, append, load as load_lessons
from src.state import DEFAULT
from src.sync import SyncError, push

TIGHT_STOP_ATR = 1.0        # a stop closer than this that gets hit is a candidate "stop_too_tight"
CHASE_TOL = 0.002           # fill beyond the entry zone by more than 0.2% is "entry_chased"
STOP_OVERSHOOT_TOL = 0.01   # exit more than 1% beyond the planned stop suggests the stop was widened


def suggest_tag(t: dict) -> dict:
    """Deterministic candidate tag + evidence. Process errors first, then outcome."""
    if t.get("status") != "closed":
        raise ValueError(f"{t.get('id')} is not closed")
    long = t["direction"] == "long"
    won = (t.get("result_usd") or 0) > 0
    followed = bool(t.get("followed_plan"))
    fill, exit_, stop = t.get("fill_price"), t.get("exit_price"), t["stop"]
    lo, hi = min(t["entry_zone"]), max(t["entry_zone"])
    evidence, flags = [], []

    if t.get("guardian_verdict") != "allow":
        flags.append("rule_broken"); evidence.append(f"guardian verdict was {t.get('guardian_verdict')}")
    if exit_ is not None and ((long and exit_ < stop * (1 - STOP_OVERSHOOT_TOL)) or (not long and exit_ > stop * (1 + STOP_OVERSHOOT_TOL))):
        flags.append("rule_broken"); evidence.append(f"exit {exit_} is >1% beyond the planned stop {stop}: stop widened or not placed")
    if fill is not None and ((long and fill > hi * (1 + CHASE_TOL)) or (not long and fill < lo * (1 - CHASE_TOL))):
        flags.append("entry_chased"); evidence.append(f"fill {fill} is outside the entry zone {t['entry_zone']}")
    if t.get("outcome") == "stop_hit" and (t.get("stop_distance_atr") or 9) < TIGHT_STOP_ATR and "rule_broken" not in flags:
        flags.append("stop_too_tight"); evidence.append(f"stopped out with stop only {t['stop_distance_atr']} ATR from entry")

    process_ok = followed and not flags
    base = {(True, True): "good_trade_good_outcome", (True, False): "good_trade_bad_outcome",
            (False, True): "bad_trade_good_outcome", (False, False): "bad_trade_bad_outcome"}[(process_ok, won)]
    if not followed:
        evidence.append(f"plan not followed: {t.get('deviation_note')}")
    primary = flags[0] if flags else base
    kind = "process" if (flags and flags[0] != "stop_too_tight") or not followed else "market"
    return {"id": t["id"], "primary": primary, "candidates": list(dict.fromkeys(flags + [base])),
            "kind_hint": kind, "outcome": t.get("outcome"), "result_usd": t.get("result_usd"),
            "followed_plan": followed, "evidence": evidence or ["plan followed; outcome is market noise"]}


def record_review(ticket_id: str, tag: str, lesson_text: str, kind: str, agent: str, date: str,
                  applied: str | None = None, journal_dir: Path = None, lessons_path: Path = None) -> dict:
    jd, lp = journal_dir or journal.JOURNAL_DIR, lessons_path or DEFAULT.lessons
    if tag not in journal.REVIEW_TAGS:
        raise ValueError(f"tag must be one of {journal.REVIEW_TAGS}")
    t = journal.load_ticket(ticket_id, jd)
    if t["status"] != "closed":
        raise ValueError(f"{ticket_id} is not closed")
    if kind == "process":
        status = f"yes, {applied}" if applied else "no"
    else:
        n = len([x for x in journal.list_tickets("closed", jd) if x.get("result_usd") is not None])
        status = f"pending backtest, n={n}"
    lesson = Lesson(date, kind, agent, lesson_text.strip(), status)
    append(lesson, lp)
    updated = journal.update_ticket(ticket_id, jd, review_tag=tag, lesson=lesson_text.strip())
    return {"ticket": updated, "lesson": lesson.as_dict()}


def unreviewed(journal_dir: Path = None) -> list[dict]:
    return [t for t in journal.list_tickets("closed", journal_dir or journal.JOURNAL_DIR) if not t.get("review_tag")]


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
    ap = argparse.ArgumentParser(description="Reviewer: suggest a tag, record tag + lesson.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("suggest"); s.add_argument("id")
    r = sub.add_parser("record"); r.add_argument("id")
    r.add_argument("--tag", required=True, choices=journal.REVIEW_TAGS)
    r.add_argument("--kind", required=True, choices=("process", "market"))
    r.add_argument("--agent", required=True)
    r.add_argument("--lesson", required=True, help="one paragraph")
    r.add_argument("--date", required=True)
    r.add_argument("--applied", help="process lessons: where it was applied, e.g. 'planner.md §rules'")
    sub.add_parser("unreviewed")
    args = ap.parse_args(argv)
    try:
        if args.cmd == "suggest":
            print(json.dumps(suggest_tag(journal.load_ticket(args.id)), indent=2))
        elif args.cmd == "record":
            print(json.dumps(record_review(args.id, args.tag, args.lesson, args.kind, args.agent, args.date, args.applied), indent=2))
            return _push(f"review {args.id}")
        else:
            for t in unreviewed():
                print(f"{t['id']}  {t['outcome']}  {t['result_usd']:+.2f}  followed_plan={t['followed_plan']}")
    except (ValueError, FileNotFoundError) as exc:
        print(f"REVIEW REFUSED: {exc}")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
