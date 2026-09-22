import pytest

from src.analyst import analyse
from src.guardian import check_ticket
from src.planner import NoTrade, build_ticket
from src.sizing import loss_if_stopped
from tests.synth import coiling, ranging, trend

DATE = "2026-09-14"


def _build(daily, weekly, account_state, settings, pair="BTC", flag="go"):
    return build_ticket(pair, DATE, analyse(daily, weekly), account_state, settings, 0.0001, flag)


def test_uptrend_ticket_geometry_sizing_and_guardian(account_state, settings):
    t = _build(trend(), trend(n=250), account_state, settings)
    lo, hi = t["entry_zone"]
    assert t["direction"] == "long" and t["strategy"] == "trend_pullback"
    assert t["stop"] < lo <= hi < t["target"]
    assert t["rr"] >= 2.0
    assert t["risk_usd"] == 25
    assert loss_if_stopped(hi, t["stop"], t["position_qty"]) == pytest.approx(25, abs=0.5)
    assert t["stop_distance_atr"] > 0 and t["funding_rate"] == 0.0001
    assert t["guardian_verdict"] is None  # attached by the caller, never by the planner
    assert check_ticket(t, account_state, [], settings).allow


def test_downtrend_ticket_is_mirror(account_state, settings):
    t = _build(trend(drift=-0.004, seed=4), trend(drift=-0.004, seed=4, n=250), account_state, settings, pair="ETH")
    lo, hi = t["entry_zone"]
    assert t["direction"] == "short"
    assert t["target"] < lo <= hi < t["stop"]
    assert t["rr"] >= 2.0
    assert check_ticket(t, account_state, [], settings).allow


def test_zone_never_beyond_current_close(account_state, settings):
    d = trend()
    t = _build(d, trend(n=250), account_state, settings)
    assert t["entry_zone"][1] <= d["close"].iloc[-1]


def test_weekly_contradiction_is_no_trade(account_state, settings):
    with pytest.raises(NoTrade, match="contradicts"):
        _build(trend(), trend(drift=-0.004, seed=4, n=250), account_state, settings)


def test_coiling_is_no_trade(account_state, settings):
    with pytest.raises(NoTrade, match="coiling"):
        _build(coiling(), trend(n=250), account_state, settings)


def test_unclassified_is_no_trade(account_state, settings):
    with pytest.raises(NoTrade, match="no clear market class"):
        _build(ranging(), trend(n=250), account_state, settings)  # mid-range: EMA in motion


def test_events_no_trade_flag(account_state, settings):
    with pytest.raises(NoTrade, match="events_scout"):
        _build(trend(), trend(n=250), account_state, settings, flag="no-trade")


def test_range_fade_or_too_narrow(account_state, settings):
    """At the low band the planner either fades it with a 2:1 target inside the
    band or refuses because the range is too narrow. Both are valid; neither
    may produce a target beyond the opposite band."""
    daily = ranging(n=306)
    try:
        t = _build(daily, trend(n=250), account_state, settings)
    except NoTrade as exc:
        assert "range too narrow" in str(exc)
    else:
        a = analyse(daily, trend(n=250))["daily"]["levels"]
        assert t["direction"] == "long" and t["strategy"] == "range_fade"
        assert t["target"] <= a["band_high"] and t["stop"] < a["band_low"]


def test_disallowed_instrument(account_state, settings):
    with pytest.raises(NoTrade):
        _build(trend(), trend(n=250), account_state, settings, pair="SOL")


def test_xrp_ticket_uses_tick_and_whole_units(account_state, settings):
    t = _build(trend(start_price=1.5), trend(n=250, start_price=1.5), account_state, settings, pair="XRP")
    assert t["pair"] == "XRP" and t["position_qty"] == int(t["position_qty"])
    for level in (t["stop"], t["target"], *t["entry_zone"]):
        assert round(level, 4) == level
    assert loss_if_stopped(t["entry_zone"][1], t["stop"], t["position_qty"]) == pytest.approx(25, rel=0.02)
    assert check_ticket(t, account_state, [], settings).allow
