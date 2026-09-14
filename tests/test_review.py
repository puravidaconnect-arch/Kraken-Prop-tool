import pytest

from src import journal
from src.lessons import load as load_lessons, pending_market
from src.report import close_ticket
from src.review import record_review, suggest_tag, unreviewed


def _closed(good_ticket, **over):
    t = {**good_ticket, "guardian_verdict": "allow", "status": "closed", "fill_price": 100200, "exit_price": 114000,
         "position_qty": 0.00385, "result_usd": 52.0, "outcome": "target_hit", "followed_plan": True,
         "deviation_note": None, "stop_distance_atr": 1.8}
    t.update(over)
    return t


def test_suggest_outcome_matrix(good_ticket):
    assert suggest_tag(_closed(good_ticket))["primary"] == "good_trade_good_outcome"
    assert suggest_tag(_closed(good_ticket, exit_price=94000, result_usd=-24, outcome="stop_hit"))["primary"] == "good_trade_bad_outcome"
    s = suggest_tag(_closed(good_ticket, followed_plan=False, deviation_note="took profit early", exit_price=105000, result_usd=18, outcome="exited_early"))
    assert s["primary"] == "bad_trade_good_outcome" and s["kind_hint"] == "process"
    assert suggest_tag(_closed(good_ticket, followed_plan=False, deviation_note="x", exit_price=94000, result_usd=-24, outcome="stop_hit"))["primary"] == "bad_trade_bad_outcome"


def test_suggest_process_flags(good_ticket):
    s = suggest_tag(_closed(good_ticket, fill_price=101500))
    assert s["primary"] == "entry_chased" and "outside the entry zone" in s["evidence"][0]
    s = suggest_tag(_closed(good_ticket, exit_price=92000, result_usd=-32, outcome="stop_hit"))
    assert s["primary"] == "rule_broken" and "stop widened" in s["evidence"][0]
    s = suggest_tag(_closed(good_ticket, exit_price=94000, result_usd=-24, outcome="stop_hit", stop_distance_atr=0.6))
    assert s["primary"] == "stop_too_tight" and s["kind_hint"] == "market"
    assert suggest_tag(_closed(good_ticket, guardian_verdict="block"))["primary"] == "rule_broken"
    with pytest.raises(ValueError):
        suggest_tag({**good_ticket, "status": "open"})


def test_record_review_writes_tag_and_lesson(repo, good_ticket):
    t = journal.new_ticket("2026-09-14", "BTC", "long", **{k: v for k, v in _closed(good_ticket).items() if k in journal.FIELDS and k not in ("id", "pair", "direction")})
    journal.save_ticket(t, repo.journal)
    assert [x["id"] for x in unreviewed(repo.journal)] == [t["id"]]

    r = record_review(t["id"], "good_trade_good_outcome", "Plan followed, target hit in 4 days. No change.", "market", "planner",
                      "2026-09-18", journal_dir=repo.journal, lessons_path=repo.lessons)
    saved = journal.load_ticket(t["id"], repo.journal)
    assert saved["review_tag"] == "good_trade_good_outcome" and saved["lesson"].startswith("Plan followed")
    assert r["lesson"]["status"] == "pending backtest, n=1" and r["lesson"]["pending"]
    assert unreviewed(repo.journal) == []
    ls = load_lessons(repo.lessons)
    assert len(ls) == 1 and ls[0].kind == "market" and ls[0].agent == "planner"
    assert pending_market(repo.lessons)[0].status == "pending backtest, n=1"  # stays pending: n < 20


def test_record_process_lesson_records_where_applied(repo, good_ticket):
    t = journal.new_ticket("2026-09-14", "ETH", "short", **{k: v for k, v in _closed(good_ticket, pair="ETH", direction="short",
                           entry_zone=[3000, 3050], stop=3200, target=2600, fill_price=2950, exit_price=2600, position_qty=0.125, result_usd=43.0).items()
                           if k in journal.FIELDS and k not in ("id", "pair", "direction")})
    journal.save_ticket(t, repo.journal)
    r = record_review(t["id"], "entry_chased", "Filled 50 below the zone. Wait for the limit.", "process", "checklist",
                      "2026-09-18", applied="checklist.md §rules of conduct", journal_dir=repo.journal, lessons_path=repo.lessons)
    assert r["lesson"]["status"] == "yes, checklist.md §rules of conduct" and not r["lesson"]["pending"]
    with pytest.raises(ValueError, match="tag must be"):
        record_review(t["id"], "meh", "x", "process", "checklist", "2026-09-18", journal_dir=repo.journal, lessons_path=repo.lessons)
    with pytest.raises(ValueError, match="risk_rules"):
        record_review(t["id"], "rule_broken", "x", "process", "guardian", "2026-09-18", applied="risk_rules.md",
                      journal_dir=repo.journal, lessons_path=repo.lessons)


def test_close_then_review_end_to_end(repo, good_ticket):
    """Phase 4 acceptance: a closed trade produces a tagged journal entry and a lesson."""
    good_ticket["guardian_verdict"] = "allow"
    t = journal.new_ticket("2026-09-14", "BTC", "long", **{k: v for k, v in good_ticket.items() if k in journal.FIELDS and k not in ("id", "pair", "direction")})
    journal.save_ticket(t, repo.journal)
    close_ticket(t["id"], fill_price=100300, exit_price=94000, position_qty=0.00385, result_usd=-24.6, opened_at="2026-09-14T10:00",
                 closed_at="2026-09-16T02:00", followed_plan=True, deviation_note=None, mid_trade_events="none", emotion_note="ok",
                 journal_dir=repo.journal)
    s = suggest_tag(journal.load_ticket(t["id"], repo.journal))
    assert s["primary"] == "good_trade_bad_outcome" and s["evidence"] == ["plan followed; outcome is market noise"]
    record_review(t["id"], s["primary"], "Stopped by a wick, plan followed. Noise.", "market", "planner", "2026-09-16",
                  journal_dir=repo.journal, lessons_path=repo.lessons)
    saved = journal.load_ticket(t["id"], repo.journal)
    assert saved["review_tag"] == "good_trade_bad_outcome" and saved["lesson"]
    assert "## 2026-09-16 — market — planner" in repo.lessons.read_text()
