"""wrap/desk units plus the Phase 3 end-to-end: plan → report → wrap → desk."""
import io
import json

from src import journal, plan
from src.desk import breached, desk, verdict, wrap_is_current
from src.events import build, save_events
from src.market_data import MarketData
from src.report import close_ticket, mark_open
from src.wrap import compute_account_state, wrap
from tests.synth import trend

D0, D1, D2 = "2026-09-14", "2026-09-15", "2026-09-16"


def _md(pair="BTC", mark=1.0):
    return MarketData(pair, trend(), trend(n=250),
                      {"symbol": f"PF_{pair}USD", "funding_rate": 0.0001, "mark_price": mark}, "x")


def _closed(id_, closed_at, result, opened_at=None):
    return {"id": id_, "status": "closed", "closed_at": closed_at, "opened_at": opened_at or closed_at, "result_usd": result}


def test_compute_account_state(account_state):
    tickets = [_closed("a", "2026-09-12T10:00", 50), _closed("b", "2026-09-14T09:00", -25, "2026-09-13T10:00"),
               _closed("c", "2026-09-14T15:00", -20, "2026-09-14T11:00"), {"id": "d", "status": "planned"}]
    s = compute_account_state(account_state, tickets, D0)
    assert s["current_balance"] == 5005 and s["drawdown_room"] == 505
    assert s["realized_pnl_today"] == -45 and s["losses_today"] == 2 and s["trades_today"] == 1
    assert s["consecutive_losses"] == 2 and s["as_of"] == D0 and s["max_drawdown_floor"] == 4500


def test_wrap_is_current_rules():
    assert wrap_is_current(D0, D1, False) == (True, "")
    assert wrap_is_current(D1, D1, False)[0]  # re-running desk on the same day is fine
    assert wrap_is_current(None, D1, True)[0]  # fresh install
    ok, why = wrap_is_current(None, D1, False)
    assert not ok and why == "Run /wrap for 2026-09-14 first."
    ok, why = wrap_is_current("2026-09-10", D1, False)
    assert not ok and why.startswith("Run /wrap for 2026-09-14 first")


def test_breached_and_verdict():
    long = {"direction": "long", "stop": 90, "target": 110}
    assert breached(long, 89) == "stop" and breached(long, 111) == "target" and breached(long, 100) is None
    short = {"direction": "short", "stop": 110, "target": 90}
    assert breached(short, 111) == "stop" and breached(short, 89) == "target"
    reads = {"BTC": {"strategy": "trend_pullback"}, "ETH": {"strategy": None}}
    assert verdict(True, "go", reads) == "TRADE"
    assert verdict(True, "caution", {"BTC": {"strategy": None}}) == "WAIT"
    assert verdict(True, "no-trade", reads) == "NO-TRADE DAY"
    assert verdict(False, "go", reads) == "NO-TRADE DAY"


def test_desk_refuses_without_wrap(repo):
    # a journal with a ticket but no wrap ever → refuse
    t = journal.new_ticket("2026-09-10", "BTC", "long", guardian_verdict="allow", status="cancelled", outcome="cancelled")
    journal.save_ticket(t, repo.journal)
    out = io.StringIO()
    assert desk(D1, repo, market_getter=_md, out=out) == 2
    assert out.getvalue().strip() == "Run /wrap for 2026-09-14 first."
    assert not any(repo.daily_log.iterdir())


def test_end_to_end_plan_report_wrap_desk(repo):
    # --- day 0: scout, plan ---------------------------------------------------
    save_events(build([], D0, 5), repo.events)
    out = io.StringIO()
    assert plan.run("BTC", date=D0, market_getter=lambda p: _md(p), out=out, paths=repo) == 0, out.getvalue()
    tid = "2026-09-14_BTC_long"
    t = journal.load_ticket(tid, repo.journal)

    # human fills, then the trade closes at target the next day
    mark_open(tid, max(t["entry_zone"]), f"{D0}T14:00", repo.journal)
    fill = max(t["entry_zone"])
    close_ticket(tid, fill_price=fill, exit_price=t["target"], position_qty=t["position_qty"],
                 result_usd=round((t["target"] - fill) * t["position_qty"] - 1.0, 2), opened_at=f"{D0}T14:00",
                 closed_at=f"{D1}T09:30", followed_plan=True, deviation_note=None, mid_trade_events="none",
                 emotion_note="calm", journal_dir=repo.journal)

    # --- day 1: wrap -----------------------------------------------------------
    r = wrap(D1, "uptrend intact, wait for next pullback", repo)
    acct = json.loads(repo.account_state.read_text())
    assert acct["current_balance"] > 5000 and acct["drawdown_room"] == round(acct["current_balance"] - 4500, 2)
    assert acct["losses_today"] == 0 and acct["consecutive_losses"] == 0 and acct["as_of"] == D1
    assert json.loads(repo.open_positions.read_text()) == []
    assert json.loads(repo.last_wrap.read_text()) == {"date": D1}
    log = (repo.daily_log / f"{D1}.md").read_text()
    assert len(log.strip().splitlines()) <= 15 and "target_hit" in log
    brief = repo.next_day_brief.read_text()
    assert "Brief for 2026-09-16" in brief and "uptrend intact" in brief
    csv_text = (repo.journal / "journal.csv").read_text()
    assert csv_text.splitlines()[0].startswith("id,pair,direction") and tid in csv_text
    assert r["unreviewed"] == [tid]  # reviewer is Phase 4

    # --- day 2: new session, desk ---------------------------------------------
    save_events(build([{"date": "2026-09-18", "name": "options expiry", "severity": "minor"}], D2, 5), repo.events)
    out = io.StringIO()
    assert desk(D2, repo, market_getter=lambda p: _md(p, mark=150000.0), out=out) == 0, out.getvalue()
    text = out.getvalue()
    assert text.startswith(f"MORNING REPORT  {D2}") and len(text.splitlines()) <= 25
    assert "VERDICT   : TRADE" in text and "events    : caution" in text and "open      : none" in text
    assert json.loads(repo.account_state.read_text())["as_of"] == D2

    # desk two days later without a wrap in between → refused
    out = io.StringIO()
    assert desk("2026-09-18", repo, market_getter=_md, out=out) == 2
    assert "Run /wrap for 2026-09-17 first" in out.getvalue()


def test_desk_demands_report_when_open_ticket_breached(repo):
    save_events(build([], D0, 5), repo.events)
    assert plan.run("BTC", date=D0, market_getter=lambda p: _md(p), out=io.StringIO(), paths=repo) == 0
    tid = "2026-09-14_BTC_long"
    t = mark_open(tid, 137000, f"{D0}T14:00", repo.journal)
    wrap(D0, "x", repo)
    assert json.loads(repo.open_positions.read_text())[0]["id"] == tid
    out = io.StringIO()
    assert desk(D1, repo, market_getter=lambda p: _md(p, mark=t["stop"] - 1), out=out) == 2
    assert out.getvalue().startswith(f"REPORT NEEDED: {tid} is open and mark")
    out = io.StringIO()
    assert desk(D1, repo, market_getter=lambda p: _md(p, mark=t["stop"] + 500), out=out) == 0
    assert "NO NEW TRADES" in out.getvalue() and "1 open position" in out.getvalue()
    assert "VERDICT   : NO-TRADE DAY" in out.getvalue()
