import pytest

from src import journal
from src.report import cancel_ticket, check_consistency, close_ticket, derive_outcome, mark_open, pending_reports


@pytest.fixture
def planned(repo, good_ticket):
    good_ticket["guardian_verdict"] = "allow"
    t = journal.new_ticket("2026-09-14", "BTC", "long", **{k: v for k, v in good_ticket.items() if k in journal.FIELDS and k not in ("id", "pair", "direction")})
    journal.save_ticket(t, repo.journal)
    return t


def test_derive_outcome_long_and_short():
    long = {"direction": "long", "stop": 94000, "target": 114000}
    assert derive_outcome(long, 94100) == "stop_hit"
    assert derive_outcome(long, 93000) == "stop_hit"
    assert derive_outcome(long, 113800) == "target_hit"
    assert derive_outcome(long, 116000) == "exited_late"
    assert derive_outcome(long, 105000) == "exited_early"
    short = {"direction": "short", "stop": 3200, "target": 2600}
    assert derive_outcome(short, 3250) == "stop_hit"
    assert derive_outcome(short, 2605) == "target_hit"
    assert derive_outcome(short, 2500) == "exited_late"
    assert derive_outcome(short, 2900) == "exited_early"


def test_consistency_checks(good_ticket):
    assert check_consistency(good_ticket, 100000, 114000, 0.00385, 52.9) == []
    assert any("opposite sign" in p for p in check_consistency(good_ticket, 100000, 114000, 0.00385, -50))
    assert any("far from gross" in p for p in check_consistency(good_ticket, 100000, 114000, 0.00385, 500))
    assert any("differs from planned" in p for p in check_consistency(good_ticket, 100000, 114000, 0.01, 140))


def test_open_then_close_flow(repo, planned):
    assert [t["id"] for t in pending_reports(repo.journal)] == [planned["id"]]
    t = mark_open(planned["id"], 100200, "2026-09-14T10:00", repo.journal)
    assert t["status"] == "open" and t["fill_price"] == 100200
    with pytest.raises(ValueError, match="only a planned ticket"):
        mark_open(planned["id"], 100200, "2026-09-14T10:00", repo.journal)

    t = close_ticket(planned["id"], fill_price=100200, exit_price=94000, position_qty=0.00385, result_usd=-24.5,
                     opened_at="2026-09-14T10:00", closed_at="2026-09-16T03:00", followed_plan=True,
                     deviation_note=None, mid_trade_events="none", emotion_note="fine", journal_dir=repo.journal)
    assert t["status"] == "closed" and t["outcome"] == "stop_hit" and t["result_usd"] == -24.5
    assert pending_reports(repo.journal) == []
    with pytest.raises(ValueError, match="already closed"):
        close_ticket(planned["id"], fill_price=1, exit_price=1, position_qty=1, result_usd=0, opened_at="", closed_at="",
                     followed_plan=True, deviation_note=None, mid_trade_events=None, emotion_note=None, journal_dir=repo.journal)


def test_close_requires_deviation_note_and_refuses_bad_numbers(repo, planned):
    kw = dict(fill_price=100200, exit_price=114000, position_qty=0.00385, result_usd=53.0, opened_at="2026-09-14T10:00",
              closed_at="2026-09-18T10:00", mid_trade_events=None, emotion_note=None, journal_dir=repo.journal)
    with pytest.raises(ValueError, match="deviation_note is required"):
        close_ticket(planned["id"], followed_plan=False, deviation_note=None, **kw)
    with pytest.raises(ValueError, match="look wrong"):
        close_ticket(planned["id"], followed_plan=True, deviation_note=None, **{**kw, "result_usd": -53.0})
    t = close_ticket(planned["id"], followed_plan=False, deviation_note="moved stop", **kw)
    assert t["outcome"] == "target_hit" and t["followed_plan"] is False


def test_cancel(repo, planned):
    t = cancel_ticket(planned["id"], "never filled", repo.journal)
    assert t["status"] == "cancelled" and t["outcome"] == "cancelled"
    with pytest.raises(ValueError):
        cancel_ticket(planned["id"], None, repo.journal)
