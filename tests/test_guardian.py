import pytest

from src.guardian import can_trade_today, check_stop_update, check_ticket


def test_good_ticket_allowed(good_ticket, account_state, settings):
    v = check_ticket(good_ticket, account_state, [], settings)
    assert v.allow, v.reasons
    assert v.verdict == "allow"


# --- the six acceptance blocks from CLAUDE.md §8 Phase 1 ---------------------

def test_blocks_altcoin(good_ticket, account_state, settings):
    good_ticket["pair"] = "SOL"
    v = check_ticket(good_ticket, account_state, [], settings)
    assert not v.allow
    assert any("SOL" in r and "not allowed" in r for r in v.reasons)


def test_blocks_risk_over_one_percent(good_ticket, account_state, settings):
    good_ticket["risk_usd"] = 51  # 1% of 5000 is 50
    good_ticket["position_qty"] = 0.00785
    v = check_ticket(good_ticket, account_state, [], settings)
    assert not v.allow
    assert any("exceeds 1% cap" in r for r in v.reasons)


def test_blocks_third_trade_after_two_losses(good_ticket, account_state, settings):
    account_state["losses_today"] = 2
    account_state["realized_pnl_today"] = -50
    assert not can_trade_today(account_state, [], settings).allow
    v = check_ticket(good_ticket, account_state, [], settings)
    assert not v.allow
    assert any("2 losses today" in r for r in v.reasons)


def test_blocks_missing_stop(good_ticket, account_state, settings):
    good_ticket["stop"] = None
    v = check_ticket(good_ticket, account_state, [], settings)
    assert not v.allow
    assert "missing stop loss" in v.reasons


def test_blocks_missing_target(good_ticket, account_state, settings):
    good_ticket["target"] = None
    v = check_ticket(good_ticket, account_state, [], settings)
    assert not v.allow
    assert "missing take profit target" in v.reasons


def test_blocks_rr_below_two(good_ticket, account_state, settings):
    good_ticket["target"] = 110000  # (110000-100500)/(100500-94000) = 1.46
    v = check_ticket(good_ticket, account_state, [], settings)
    assert not v.allow
    assert any("reward-to-risk" in r and "below minimum" in r for r in v.reasons)


def test_rr_uses_worst_case_entry(good_ticket, account_state, settings):
    # 2:1 from the bottom of the zone but not from the top → block
    good_ticket["target"] = 111000  # from 99500: 11500/5500 = 2.09; from 100500: 10500/6500 = 1.62
    v = check_ticket(good_ticket, account_state, [], settings)
    assert not v.allow


def test_blocks_second_concurrent_position(good_ticket, account_state, settings):
    open_positions = [{"id": "2026-09-13_ETH_long", "pair": "ETH", "status": "open"}]
    assert not can_trade_today(account_state, open_positions, settings).allow
    v = check_ticket(good_ticket, account_state, open_positions, settings)
    assert not v.allow
    assert any("open position" in r for r in v.reasons)


# --- other rules -------------------------------------------------------------

def test_blocks_when_daily_cap_reached(good_ticket, account_state, settings):
    account_state["realized_pnl_today"] = -100
    account_state["losses_today"] = 1
    v = check_ticket(good_ticket, account_state, [], settings)
    assert not v.allow
    assert any("daily loss cap" in r for r in v.reasons)


def test_blocks_when_risk_exceeds_remaining_daily_budget(good_ticket, account_state, settings):
    account_state["realized_pnl_today"] = -80  # $20 left, ticket risks $25
    account_state["losses_today"] = 1
    v = check_ticket(good_ticket, account_state, [], settings)
    assert not v.allow
    assert any("remaining daily budget" in r for r in v.reasons)


def test_blocks_when_no_drawdown_room(good_ticket, account_state, settings):
    account_state["drawdown_room"] = 0
    v = check_ticket(good_ticket, account_state, [], settings)
    assert not v.allow
    assert "no drawdown room left" in v.reasons


def test_blocks_no_trade_events_flag_without_override(good_ticket, account_state, settings):
    good_ticket["events_flag"] = "no-trade"
    assert not check_ticket(good_ticket, account_state, [], settings).allow
    good_ticket["events_override"] = True
    assert check_ticket(good_ticket, account_state, [], settings).allow


def test_blocks_bad_long_geometry(good_ticket, account_state, settings):
    good_ticket["stop"] = 101000  # stop above entry on a long
    v = check_ticket(good_ticket, account_state, [], settings)
    assert not v.allow
    assert any("long geometry invalid" in r for r in v.reasons)


def test_short_ticket_allowed(account_state, settings):
    ticket = {
        "pair": "ETH", "direction": "short", "entry_zone": [3000, 3050],
        "stop": 3200, "target": 2600, "risk_usd": 25, "position_qty": 0.125,
        "events_flag": "go",
    }
    v = check_ticket(ticket, account_state, [], settings)
    assert v.allow, v.reasons


def test_blocks_when_loss_if_stopped_exceeds_planned_risk(good_ticket, account_state, settings):
    good_ticket["position_qty"] = 0.01  # 0.01 * 6500 = $65 vs planned $25
    v = check_ticket(good_ticket, account_state, [], settings)
    assert not v.allow
    assert any("loss if stopped" in r for r in v.reasons)


def test_blocks_invalid_direction(good_ticket, account_state, settings):
    good_ticket["direction"] = "buy"
    assert not check_ticket(good_ticket, account_state, [], settings).allow


def test_stop_never_widened():
    long_ticket = {"direction": "long", "stop": 94000}
    assert check_stop_update(long_ticket, 95000).allow      # tighten ok
    assert check_stop_update(long_ticket, 94000).allow      # unchanged ok
    assert not check_stop_update(long_ticket, 93000).allow  # widen blocked
    short_ticket = {"direction": "short", "stop": 3200}
    assert check_stop_update(short_ticket, 3150).allow
    assert not check_stop_update(short_ticket, 3250).allow


def test_allows_xrp(good_ticket, account_state, settings):
    good_ticket["pair"] = "XRP"
    assert check_ticket(good_ticket, account_state, [], settings).allow
