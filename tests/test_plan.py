import io
import json

import pytest

from src import plan
from src.events import build, save_events
from src.market_data import MarketData, MarketDataError
from tests.synth import coiling, trend

DATE = "2026-09-14"


def _md(daily=None, weekly=None):
    return MarketData("BTC", daily if daily is not None else trend(),
                      weekly if weekly is not None else trend(n=250),
                      {"symbol": "PF_XBTUSD", "funding_rate": 0.0001, "mark_price": 1.0}, "2026-09-14T00:00:00+00:00")


@pytest.fixture
def scouted(repo):
    save_events(build([], DATE, 5), repo.events)
    return repo


def test_plan_prints_checklist_and_saves_ticket(scouted):
    out = io.StringIO()
    rc = plan.run("BTC", date=DATE, market_getter=lambda p: _md(), out=out, paths=scouted)
    text = out.getvalue()
    assert rc == 0, text
    assert "MARKET READ  BTC" in text and "TRADE TICKET  2026-09-14_BTC_long" in text
    assert "PRE-TRADE CHECKLIST" in text and "VERDICT: GO" in text and "PF_XBTUSD" in text
    assert '"guardian_verdict": "allow"' in text and "_planner_note" not in text
    saved = json.loads((scouted.journal / "2026-09-14_BTC_long.json").read_text())
    assert saved["status"] == "planned" and saved["events_flag"] == "go"


def test_plan_requires_events_scouted_today(repo):
    out = io.StringIO()
    rc = plan.run("BTC", date=DATE, market_getter=lambda p: _md(), out=out, paths=repo)
    assert rc == 2 and "events not scouted today" in out.getvalue()
    save_events(build([], "2026-09-10", 5), repo.events)  # stale
    assert plan.run("BTC", date=DATE, market_getter=lambda p: _md(), out=io.StringIO(), paths=repo) == 2


def test_plan_reads_no_trade_flag_from_store(repo):
    save_events(build([{"date": "2026-09-17", "name": "FOMC", "severity": "major"}], DATE, 5), repo.events)
    out = io.StringIO()
    assert plan.run("BTC", date=DATE, market_getter=lambda p: _md(), out=out, paths=repo) == 2
    assert "NO TRADE: events_scout flagged no-trade" in out.getvalue()


def test_plan_no_trade_is_one_line_and_saves_nothing(scouted):
    out = io.StringIO()
    rc = plan.run("BTC", date=DATE, market_getter=lambda p: _md(daily=coiling()), out=out, paths=scouted)
    assert rc == 2
    assert [l for l in out.getvalue().splitlines() if l.startswith("NO TRADE")] == ["NO TRADE: coiling: wait for a daily close outside the range"]
    assert not list(scouted.journal.glob("*.json"))


def test_plan_stops_on_market_data_failure(scouted):
    def boom(p):
        raise MarketDataError("api.kraken.com unreachable")
    out = io.StringIO()
    assert plan.run("BTC", date=DATE, market_getter=boom, out=out, paths=scouted) == 1
    assert out.getvalue().startswith("MARKET DATA FAILED: api.kraken.com unreachable")


def test_plan_guardian_precheck_blocks_before_fetching(scouted, account_state):
    account_state.update(losses_today=2, as_of=DATE)
    scouted.account_state.write_text(json.dumps(account_state))
    called = []
    out = io.StringIO()
    assert plan.run("BTC", date=DATE, market_getter=lambda p: called.append(p), out=out, paths=scouted) == 2
    assert not called and out.getvalue().startswith("NO TRADE TODAY (guardian)")


def test_plan_rolls_intraday_counters_on_a_new_day(scouted, account_state):
    account_state.update(losses_today=2, realized_pnl_today=-50, as_of="2026-09-13")
    scouted.account_state.write_text(json.dumps(account_state))
    out = io.StringIO()
    assert plan.run("BTC", date=DATE, market_getter=lambda p: _md(), out=out, paths=scouted) == 0
    rolled = json.loads(scouted.account_state.read_text())
    assert rolled["losses_today"] == 0 and rolled["realized_pnl_today"] == 0 and rolled["as_of"] == DATE


def test_plan_rejects_altcoin_and_cli_override(scouted):
    out = io.StringIO()
    assert plan.run("SOL", date=DATE, market_getter=lambda p: _md(), out=out, paths=scouted) == 2
    assert "not allowed" in out.getvalue()
    out = io.StringIO()
    assert plan.run("BTC", "no-trade", DATE, market_getter=lambda p: _md(), out=out, paths=scouted) == 2
    assert "NO TRADE: events_scout" in out.getvalue()
