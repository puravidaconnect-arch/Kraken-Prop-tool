"""Load/save the JSON config and state files. No logic here beyond rolling
the intraday counters onto a new day."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Paths:
    root: Path

    @property
    def settings(self): return self.root / "config" / "settings.json"
    @property
    def account_state(self): return self.root / "state" / "account_state.json"
    @property
    def open_positions(self): return self.root / "state" / "open_positions.json"
    @property
    def last_wrap(self): return self.root / "state" / "last_wrap.json"
    @property
    def events(self): return self.root / "state" / "events.json"
    @property
    def next_day_brief(self): return self.root / "state" / "next_day_brief.md"
    @property
    def journal(self): return self.root / "journal"
    @property
    def daily_log(self): return self.root / "daily_log"
    @property
    def lessons(self): return self.root / "lessons.md"


DEFAULT = Paths(ROOT)
SETTINGS_PATH, ACCOUNT_STATE_PATH = DEFAULT.settings, DEFAULT.account_state
OPEN_POSITIONS_PATH, LAST_WRAP_PATH = DEFAULT.open_positions, DEFAULT.last_wrap

INTRADAY_FIELDS = ("realized_pnl_today", "losses_today", "trades_today")


def load_json(path: Path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def load_settings(path: Path = SETTINGS_PATH) -> dict:
    return load_json(path)


def load_account_state(path: Path = ACCOUNT_STATE_PATH) -> dict:
    return load_json(path)


def save_account_state(state: dict, path: Path = ACCOUNT_STATE_PATH) -> None:
    save_json(path, state)


def load_open_positions(path: Path = OPEN_POSITIONS_PATH) -> list:
    return load_json(path)


def save_open_positions(positions: list, path: Path = OPEN_POSITIONS_PATH) -> None:
    save_json(path, positions)


def load_last_wrap(path: Path = LAST_WRAP_PATH) -> dict:
    return load_json(path) if path.exists() else {"date": None}


def save_last_wrap(date: str, path: Path = LAST_WRAP_PATH) -> None:
    save_json(path, {"date": date})


def roll_day(state: dict, today: str) -> dict:
    """Intraday counters belong to ``as_of``. On a later day they start at zero.
    Balance, floor and drawdown_room carry over untouched (drawdown never resets)."""
    if state.get("as_of", "") >= today:
        return dict(state)
    rolled = {**state, "as_of": today}
    for k in INTRADAY_FIELDS:
        rolled[k] = 0
    return rolled
