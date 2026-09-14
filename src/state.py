"""Load/save the JSON config and state files. No logic here, just I/O."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SETTINGS_PATH = ROOT / "config" / "settings.json"
ACCOUNT_STATE_PATH = ROOT / "state" / "account_state.json"
OPEN_POSITIONS_PATH = ROOT / "state" / "open_positions.json"
LAST_WRAP_PATH = ROOT / "state" / "last_wrap.json"


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
    return load_json(path)


def save_last_wrap(date: str, path: Path = LAST_WRAP_PATH) -> None:
    save_json(path, {"date": date})
