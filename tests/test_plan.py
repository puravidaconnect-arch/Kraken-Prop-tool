import io

import pytest

from src import plan
from src.market_data import MarketData, MarketDataError
from tests.synth import coiling, trend


def _md(daily=None, weekly=None):
    return MarketData("BTC", daily if daily is not None else trend(),
                      weekly if weekly is not None else trend(n=250),
                      {"symbol": "PF_XBTUSD", "funding_rate": 0.0001, "mark_price": 1.0}, "2026-09-14T00:00:00+00:00")


@pytest.fixture
def isolated(monkeypatch, tmp_path, settings, account_state):
    monkeypatch.setattr(plan, "load_settings", lambda: settings)
    monkeypatch.setattr(plan, "load_account_state", lambda: account_state)
    monkeypatch.setattr(plan, "load_open_positions", lambda: [])
    monkeypatch.setattr(plan.journal, "JOURNAL_DIR", tmp_path)
    return tmp_path


def test_plan_prints_and_saves_ticket(isolated):
    out = io.StringIO()
    rc = plan.run("BTC", "go", "2026-09-14", market_getter=lambda p: _md(), out=out)
    text = out.getvalue()
    assert rc == 0
    assert "MARKET READ  BTC" in text and "TRADE TICKET  2026-09-14_BTC_long" in text
    assert '"guardian_verdict": "allow"' in text
    assert (isolated / "2026-09-14_BTC_long.json").exists()
    assert "_planner_note" not in text


def test_plan_no_trade_is_one_line_and_saves_nothing(isolated):
    out = io.StringIO()
    rc = plan.run("BTC", "go", "2026-09-14", market_getter=lambda p: _md(daily=coiling()), out=out)
    assert rc == 2
    assert [l for l in out.getvalue().splitlines() if l.startswith("NO TRADE")] == ["NO TRADE: coiling: wait for a daily close outside the range"]
    assert not list(isolated.glob("*.json"))


def test_plan_stops_on_market_data_failure(isolated):
    def boom(p):
        raise MarketDataError("api.kraken.com unreachable")
    out = io.StringIO()
    assert plan.run("BTC", market_getter=boom, out=out) == 1
    assert out.getvalue().startswith("MARKET DATA FAILED: api.kraken.com unreachable")


def test_plan_guardian_precheck_blocks_before_fetching(isolated, account_state):
    account_state["losses_today"] = 2
    called = []
    out = io.StringIO()
    assert plan.run("BTC", market_getter=lambda p: called.append(p), out=out) == 2
    assert not called and out.getvalue().startswith("NO TRADE TODAY (guardian)")


def test_plan_rejects_altcoin(isolated):
    out = io.StringIO()
    assert plan.run("SOL", market_getter=lambda p: _md(), out=out) == 2
    assert "not allowed" in out.getvalue()


def test_plan_events_no_trade(isolated):
    out = io.StringIO()
    assert plan.run("BTC", "no-trade", market_getter=lambda p: _md(), out=out) == 2
    assert "NO TRADE: events_scout" in out.getvalue()
