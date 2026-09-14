import pytest

from src.sizing import SizingError, loss_if_stopped, reward_to_risk, size_position


def test_spec_example_sizing():
    s = size_position(entry=100000, stop=94000, starting_balance=5000, risk_pct=0.005)
    assert s.risk_usd == 25
    assert s.stop_distance_pct == 6.0
    assert s.position_usd == pytest.approx(416.67, abs=0.01)
    assert s.position_qty == pytest.approx(0.00417, abs=1e-5)
    assert s.leverage_effective == pytest.approx(0.0833, abs=1e-4)


def test_short_sizing_uses_absolute_distance():
    s = size_position(entry=3000, stop=3150, starting_balance=5000, risk_pct=0.005)
    assert s.stop_distance_pct == 5.0
    assert s.position_usd == 500


def test_loss_if_stopped_matches_planned_risk():
    s = size_position(entry=100000, stop=94000, starting_balance=5000, risk_pct=0.005)
    assert loss_if_stopped(100000, 94000, s.position_qty) == pytest.approx(25, abs=0.5)


def test_zero_stop_distance_raises():
    with pytest.raises(SizingError, match="stop equals entry"):
        size_position(entry=100000, stop=100000, starting_balance=5000, risk_pct=0.005)


def test_risk_above_one_percent_raises():
    with pytest.raises(SizingError, match="exceeds hard cap"):
        size_position(entry=100000, stop=94000, starting_balance=5000, risk_pct=0.011)


def test_leverage_cap_raises():
    # 0.1% stop → position 25 / 0.001 = $25,000 = 5x on $5,000; cap 4x → raise
    with pytest.raises(SizingError, match="exceeds cap"):
        size_position(entry=100000, stop=99900, starting_balance=5000, risk_pct=0.005, leverage_cap=4)


def test_leverage_uses_current_balance_when_given():
    # same trade, cap 5x, but balance has fallen to $4,800 → 5.2x → raise
    with pytest.raises(SizingError, match="exceeds cap"):
        size_position(entry=100000, stop=99900, starting_balance=5000, risk_pct=0.005,
                      current_balance=4800, leverage_cap=5)


@pytest.mark.parametrize("entry,stop", [(0, 94000), (100000, 0), (-1, 5)])
def test_bad_prices_raise(entry, stop):
    with pytest.raises(SizingError):
        size_position(entry=entry, stop=stop, starting_balance=5000, risk_pct=0.005)


def test_reward_to_risk():
    assert reward_to_risk(100000, 94000, 112000) == pytest.approx(2.0)
    assert reward_to_risk(3000, 3150, 2700) == pytest.approx(2.0)
    with pytest.raises(SizingError):
        reward_to_risk(100, 100, 120)
