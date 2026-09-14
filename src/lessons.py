"""Read/append/promote entries in lessons.md (CLAUDE.md §7 format).

## 2026-09-20 — process — analyst
Called uptrend with flat 200 EMA. Add slope check. [applied: yes, analyst.md §rules]

## 2026-09-22 — market — planner
Stop at 1.5×ATR hit by wick twice. Candidate: 2×ATR. [status: pending backtest, n=6]
"""
from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from pathlib import Path

from src.state import DEFAULT

KINDS = ("process", "market")
AGENTS = ("guardian", "market_data", "analyst", "events_scout", "planner", "checklist", "reviewer", "coordinator")
MIN_TRADES_FOR_MARKET_RULE = 20
HEAD = re.compile(r"^## (\d{4}-\d{2}-\d{2}) — (process|market) — (\w+)\s*$")


@dataclass
class Lesson:
    date: str
    kind: str
    agent: str
    text: str
    status: str  # process: "applied: yes, <where>" / "applied: no"; market: "pending backtest, n=6" / "applied 2026-..."

    @property
    def pending(self) -> bool:
        return self.kind == "market" and self.status.startswith("pending")

    def render(self) -> str:
        tag = f"[applied: {self.status}]" if self.kind == "process" else f"[status: {self.status}]"
        return f"## {self.date} — {self.kind} — {self.agent}\n{self.text} {tag}\n"

    def as_dict(self) -> dict:
        return {**asdict(self), "pending": self.pending}


def parse(text: str) -> list[Lesson]:
    lessons, head, body = [], None, []

    def flush():
        if head:
            para = " ".join(l.strip() for l in body if l.strip())
            m = re.search(r"\[(applied|status): (.*?)\]\s*$", para)
            status = m.group(2) if m else ("no" if head[1] == "process" else "pending backtest, n=?")
            lessons.append(Lesson(*head, para[: m.start()].strip() if m else para, status))

    for line in text.splitlines():
        m = HEAD.match(line)
        if m:
            flush()
            head, body = (m.group(1), m.group(2), m.group(3)), []
        elif head:
            body.append(line)
    flush()
    return lessons


def load(path: Path = DEFAULT.lessons) -> list[Lesson]:
    return parse(path.read_text(encoding="utf-8")) if path.exists() else []


def append(lesson: Lesson, path: Path = DEFAULT.lessons) -> None:
    if lesson.kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}")
    if lesson.agent not in AGENTS:
        raise ValueError(f"agent must be one of {AGENTS}")
    if "risk_rules" in lesson.status:
        raise ValueError("the reviewer never edits risk_rules.md; only the human does")
    existing = path.read_text(encoding="utf-8") if path.exists() else "# Lessons\n"
    if not existing.endswith("\n"):
        existing += "\n"
    path.write_text(existing + "\n" + lesson.render(), encoding="utf-8")


def pending_market(path: Path = DEFAULT.lessons) -> list[Lesson]:
    return [l for l in load(path) if l.pending]


def can_promote(n_closed_trades: int, backtest_improved: bool) -> tuple[bool, str]:
    """A market lesson becomes a rule only with n ≥ 20 trades AND a better backtest."""
    if n_closed_trades < MIN_TRADES_FOR_MARKET_RULE:
        return False, f"n={n_closed_trades} < {MIN_TRADES_FOR_MARKET_RULE} closed trades"
    if not backtest_improved:
        return False, "backtest did not improve"
    return True, "ok"


def set_status(date: str, agent: str, new_status: str, path: Path = DEFAULT.lessons) -> Lesson:
    """Rewrite the status tag of one lesson (matched by date + agent)."""
    lessons = load(path)
    hits = [l for l in lessons if l.date == date and l.agent == agent]
    if len(hits) != 1:
        raise ValueError(f"expected exactly one lesson for {date} {agent}, found {len(hits)}")
    hits[0].status = new_status
    header = path.read_text(encoding="utf-8").split("\n## ", 1)[0].rstrip("\n") if path.exists() else "# Lessons"
    path.write_text(header + "\n\n" + "\n".join(l.render() for l in lessons), encoding="utf-8")
    return hits[0]


def main(argv=None) -> int:
    """python -m src.lessons pending | promote --date D --agent A --evals-before X --evals-after Y --backtest "..." """
    import argparse
    import json
    from src import journal
    ap = argparse.ArgumentParser(description="Lessons: list pending market lessons, promote one to a rule.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("pending")
    sub.add_parser("list")
    pr = sub.add_parser("promote"); pr.add_argument("--date", required=True); pr.add_argument("--agent", required=True)
    pr.add_argument("--backtest-improved", choices=("yes", "no"), required=True)
    pr.add_argument("--evals-before", required=True); pr.add_argument("--evals-after", required=True)
    pr.add_argument("--applied", required=True, help="where the rule changed, e.g. 'planner.py PLANNER_PARAMS min_stop_atr=1.0'")
    pr.add_argument("--today", required=True)
    args = ap.parse_args(argv)
    n = len([t for t in journal.list_tickets("closed") if t.get("result_usd") is not None])
    if args.cmd in ("pending", "list"):
        for l in (pending_market() if args.cmd == "pending" else load()):
            print(f"{l.date}  {l.kind:<7} {l.agent:<12} [{l.status}]  {l.text[:90]}")
        if args.cmd == "pending":
            print(f"closed trades n={n}; market rules need n ≥ {MIN_TRADES_FOR_MARKET_RULE} and an improved backtest")
        return 0
    ok, why = can_promote(n, args.backtest_improved == "yes")
    if not ok:
        print(f"PROMOTION REFUSED: {why}")
        return 2
    if "risk_rules" in args.applied:
        print("PROMOTION REFUSED: risk_rules.md is edited only by the human, never via a lesson")
        return 2
    l = set_status(args.date, args.agent, f"applied {args.today}, n={n}, evals {args.evals_before} → {args.evals_after}, {args.applied}")
    print(json.dumps(l.as_dict(), indent=2))
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
