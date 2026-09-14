"""Journal: one JSON file per trade in journal/. The JSON is the single source
of truth. journal.csv is a view only and is never read back."""
from __future__ import annotations

import csv
from pathlib import Path

from src.state import ROOT, load_json, save_json

JOURNAL_DIR = ROOT / "journal"
CSV_PATH = JOURNAL_DIR / "journal.csv"

STATUSES = ("planned", "open", "closed", "cancelled")
OUTCOMES = ("stop_hit", "target_hit", "exited_early", "exited_late", "cancelled")
REVIEW_TAGS = (
    "good_trade_bad_outcome", "bad_trade_good_outcome", "good_trade_good_outcome",
    "bad_trade_bad_outcome", "rule_broken", "stop_too_tight", "entry_chased",
)

# Column order for the ticket JSON and the CSV export.
FIELDS = [
    "id", "pair", "direction", "strategy", "market_class", "entry_zone",
    "stop", "target", "stop_distance_pct", "stop_distance_atr", "rr",
    "risk_usd", "position_usd", "position_qty", "leverage_effective",
    "funding_rate", "events_flag", "guardian_verdict", "status",
    "opened_at", "closed_at", "fill_price", "exit_price", "outcome",
    "result_usd", "followed_plan", "deviation_note", "mid_trade_events",
    "emotion_note", "review_tag", "lesson",
]


def make_id(date: str, pair: str, direction: str) -> str:
    return f"{date}_{pair}_{direction}"


def new_ticket(date: str, pair: str, direction: str, **fields) -> dict:
    """Blank ticket with every field present, then overlaid with ``fields``."""
    ticket = {k: None for k in FIELDS}
    ticket.update(
        id=make_id(date, pair, direction), pair=pair, direction=direction,
        market_class={"daily": None, "weekly": None}, status="planned",
    )
    unknown = set(fields) - set(FIELDS)
    if unknown:
        raise KeyError(f"unknown ticket fields: {sorted(unknown)}")
    ticket.update(fields)
    return ticket


def ticket_path(ticket_id: str, journal_dir: Path = JOURNAL_DIR) -> Path:
    return journal_dir / f"{ticket_id}.json"


def save_ticket(ticket: dict, journal_dir: Path = JOURNAL_DIR) -> Path:
    if ticket.get("status") not in STATUSES:
        raise ValueError(f"invalid status {ticket.get('status')!r}")
    if ticket.get("guardian_verdict") is None:
        raise ValueError("refusing to save a ticket without a guardian verdict")
    if ticket.get("outcome") not in (None, *OUTCOMES):
        raise ValueError(f"invalid outcome {ticket['outcome']!r}")
    if ticket.get("review_tag") not in (None, *REVIEW_TAGS):
        raise ValueError(f"invalid review_tag {ticket['review_tag']!r}")
    path = ticket_path(ticket["id"], journal_dir)
    save_json(path, {k: ticket.get(k) for k in FIELDS})
    return path


def load_ticket(ticket_id: str, journal_dir: Path = JOURNAL_DIR) -> dict:
    return load_json(ticket_path(ticket_id, journal_dir))


def update_ticket(ticket_id: str, journal_dir: Path = JOURNAL_DIR, **fields) -> dict:
    ticket = load_ticket(ticket_id, journal_dir)
    unknown = set(fields) - set(FIELDS)
    if unknown:
        raise KeyError(f"unknown ticket fields: {sorted(unknown)}")
    ticket.update(fields)
    save_ticket(ticket, journal_dir)
    return ticket


def list_tickets(status: str | None = None, journal_dir: Path = JOURNAL_DIR) -> list[dict]:
    """All tickets sorted by id (date first). Optionally filter by status."""
    tickets = [load_json(p) for p in sorted(journal_dir.glob("*.json"))]
    if status is not None:
        tickets = [t for t in tickets if t.get("status") == status]
    return tickets


def tickets_closed_on(date: str, journal_dir: Path = JOURNAL_DIR) -> list[dict]:
    return [t for t in list_tickets("closed", journal_dir) if (t.get("closed_at") or "")[:10] == date]


def summarise(tickets: list[dict]) -> dict:
    closed = [t for t in tickets if t.get("status") == "closed" and t.get("result_usd") is not None]
    wins = [t for t in closed if t["result_usd"] > 0]
    losses = [t for t in closed if t["result_usd"] < 0]
    total = sum(t["result_usd"] for t in closed)
    return {
        "n_total": len(tickets),
        "n_closed": len(closed),
        "n_wins": len(wins),
        "n_losses": len(losses),
        "win_rate": round(len(wins) / len(closed), 3) if closed else None,
        "total_pnl_usd": round(total, 2),
        "avg_pnl_usd": round(total / len(closed), 2) if closed else None,
        "followed_plan_rate": (
            round(sum(1 for t in closed if t.get("followed_plan")) / len(closed), 3) if closed else None
        ),
    }


def export_csv(journal_dir: Path = JOURNAL_DIR, csv_path: Path = CSV_PATH) -> Path:
    """Flat one-row-per-trade CSV. View only: nothing ever reads this back."""
    tickets = list_tickets(journal_dir=journal_dir)
    columns = [c for c in FIELDS if c not in ("market_class", "entry_zone")]
    columns[3:3] = ["market_class_daily", "market_class_weekly", "entry_low", "entry_high"]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        for t in tickets:
            row = {k: t.get(k) for k in FIELDS if k not in ("market_class", "entry_zone")}
            mc = t.get("market_class") or {}
            zone = t.get("entry_zone") or [None, None]
            row.update(
                market_class_daily=mc.get("daily"), market_class_weekly=mc.get("weekly"),
                entry_low=zone[0], entry_high=zone[1],
            )
            writer.writerow(row)
    return csv_path
