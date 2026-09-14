import os

os.environ["STUDIO_NO_SYNC"] = "1"  # tests never touch git or the remote

import pytest


@pytest.fixture
def settings():
    return {
        "starting_balance": 5000,
        "risk_pct": 0.005,
        "max_risk_pct": 0.01,
        "daily_loss_cap_pct": 0.02,
        "max_drawdown_pct": 0.10,
        "leverage_cap": 5,
        "instruments": ["BTC", "ETH"],
        "hold_window_days": 5,
        "min_rr": 2.0,
        "max_losses_per_day": 2,
        "max_open_positions": 1,
    }


@pytest.fixture
def account_state():
    return {
        "starting_balance": 5000,
        "current_balance": 5000,
        "max_drawdown_floor": 4500,
        "drawdown_room": 500,
        "daily_loss_cap": 100,
        "realized_pnl_today": 0,
        "losses_today": 0,
        "trades_today": 0,
        "consecutive_losses": 0,
        "as_of": "2026-09-14",
    }


@pytest.fixture
def good_ticket():
    """The §5 example: BTC long, worst-case entry 100500, stop 94000, target 112000."""
    return {
        "id": "2026-09-14_BTC_long",
        "pair": "BTC",
        "direction": "long",
        "strategy": "trend_pullback",
        "market_class": {"daily": "uptrend", "weekly": "uptrend"},
        "entry_zone": [99500, 100500],
        "stop": 94000,
        "target": 114000,
        "rr": 2.08,
        "risk_usd": 25,
        "position_usd": 386.54,
        "position_qty": 0.00385,
        "leverage_effective": 0.0773,
        "funding_rate": 0.0001,
        "events_flag": "go",
        "guardian_verdict": None,
        "status": "planned",
    }


@pytest.fixture
def repo(tmp_path, settings, account_state):
    """A throwaway repo root with config/state/journal laid out like the real one."""
    import json
    from src.state import Paths
    p = Paths(tmp_path)
    for d in (p.journal, p.daily_log, p.settings.parent, p.account_state.parent):
        d.mkdir(parents=True, exist_ok=True)
    p.settings.write_text(json.dumps(settings))
    p.account_state.write_text(json.dumps(account_state))
    p.open_positions.write_text("[]")
    p.lessons.write_text("# Lessons\n")
    return p
