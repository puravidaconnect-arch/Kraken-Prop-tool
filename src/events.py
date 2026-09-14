"""Store for events_scout results. The agent does the web search; this file
holds the verdict so /plan, /wrap and /desk read the same thing."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date as _date, timedelta
from pathlib import Path

from src.state import DEFAULT, load_json, save_json

FLAGS = ("go", "caution", "no-trade")
SEVERITIES = ("major", "minor")


def window_end(start: str, hold_window_days: int) -> str:
    """Crypto trades every day, so N trading days = N calendar days."""
    return (_date.fromisoformat(start) + timedelta(days=hold_window_days)).isoformat()


def flag_for(events: list[dict], start: str, hold_window_days: int) -> str:
    """Deterministic flag: any major event inside the window → no-trade,
    any minor → caution, else go."""
    end = window_end(start, hold_window_days)
    inside = [e for e in events if start <= e["date"] <= end]
    if any(e["severity"] == "major" for e in inside):
        return "no-trade"
    if inside:
        return "caution"
    return "go"


def build(events: list[dict], as_of: str, hold_window_days: int, source: str = "events_scout") -> dict:
    for e in events:
        _date.fromisoformat(e["date"])
        if e["severity"] not in SEVERITIES:
            raise ValueError(f"severity must be one of {SEVERITIES}: {e}")
    events = sorted(events, key=lambda e: e["date"])
    return {
        "as_of": as_of,
        "window_end": window_end(as_of, hold_window_days),
        "flag": flag_for(events, as_of, hold_window_days),
        "events": events,
        "source": source,
    }


def save_events(data: dict, path: Path = DEFAULT.events) -> None:
    save_json(path, data)


def load_events(path: Path = DEFAULT.events) -> dict | None:
    return load_json(path) if path.exists() else None


def fresh_flag(today: str, path: Path = DEFAULT.events) -> tuple[str | None, dict | None]:
    """The stored flag if events_scout ran today, else None."""
    data = load_events(path)
    if data and data.get("as_of") == today:
        return data["flag"], data
    return None, data


def in_window(data: dict | None, start: str) -> list[dict]:
    if not data:
        return []
    return [e for e in data["events"] if start <= e["date"] <= data["window_end"]]


def parse_event(text: str) -> dict:
    """'2026-09-17|FOMC rate decision|major' → dict."""
    parts = [p.strip() for p in text.split("|")]
    if len(parts) != 3:
        raise ValueError(f"event must be 'YYYY-MM-DD|name|major|minor': {text!r}")
    return {"date": parts[0], "name": parts[1], "severity": parts[2]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Record the events_scout verdict.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("set", help="store today's scouted events")
    s.add_argument("--date", default=_date.today().isoformat())
    s.add_argument("--hold-window-days", type=int, default=None)
    s.add_argument("--event", action="append", default=[], help="'YYYY-MM-DD|name|major|minor' (repeatable)")
    s.add_argument("--override", action="store_true", help="human explicitly overrides a no-trade flag to caution")
    sub.add_parser("show")
    args = ap.parse_args(argv)

    if args.cmd == "show":
        print(json.dumps(load_events(), indent=2))
        return 0
    days = args.hold_window_days or load_json(DEFAULT.settings)["hold_window_days"]
    data = build([parse_event(e) for e in args.event], args.date, days)
    if args.override and data["flag"] == "no-trade":
        data["flag"], data["override"] = "caution", True
    save_events(data)
    print(json.dumps(data, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
