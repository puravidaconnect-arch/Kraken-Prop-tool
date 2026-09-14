import pytest

from src.lessons import Lesson, append, can_promote, load, parse, pending_market, set_status

SAMPLE = """# Lessons

## 2026-09-20 — process — analyst
Called uptrend with flat 200 EMA. Add slope check. [applied: yes, analyst.md §rules]

## 2026-09-22 — market — planner
Stop at 1.5×ATR hit by wick twice this month. Candidate: 2×ATR. [status: pending backtest, n=6]
"""


def test_parse_spec_format():
    ls = parse(SAMPLE)
    assert [(l.date, l.kind, l.agent) for l in ls] == [("2026-09-20", "process", "analyst"), ("2026-09-22", "market", "planner")]
    assert ls[0].text == "Called uptrend with flat 200 EMA. Add slope check." and ls[0].status == "yes, analyst.md §rules"
    assert ls[1].status == "pending backtest, n=6" and ls[1].pending and not ls[0].pending


def test_render_round_trips():
    for l in parse(SAMPLE):
        assert parse(l.render()) == [l]


def test_append_and_pending(tmp_path):
    path = tmp_path / "lessons.md"
    append(Lesson("2026-09-14", "market", "planner", "Stops too tight.", "pending backtest, n=1"), path)
    append(Lesson("2026-09-15", "process", "analyst", "Misread weekly.", "yes, analyst.md §judgment"), path)
    assert path.read_text().startswith("# Lessons\n")
    assert [l.date for l in load(path)] == ["2026-09-14", "2026-09-15"]
    assert [l.date for l in pending_market(path)] == ["2026-09-14"]
    with pytest.raises(ValueError, match="risk_rules"):
        append(Lesson("2026-09-16", "process", "guardian", "x", "yes, risk_rules.md"), path)
    with pytest.raises(ValueError):
        append(Lesson("2026-09-16", "vibes", "guardian", "x", "no"), path)


def test_market_rule_gate():
    assert can_promote(19, True) == (False, "n=19 < 20 closed trades")
    assert can_promote(20, False) == (False, "backtest did not improve")
    assert can_promote(20, True) == (True, "ok")


def test_set_status_rewrites_one_entry(tmp_path):
    path = tmp_path / "lessons.md"
    path.write_text(SAMPLE)
    l = set_status("2026-09-22", "planner", "applied 2026-12-01, n=24, evals 80.0 → 85.0", path)
    assert not l.pending
    ls = load(path)
    assert ls[0].status == "yes, analyst.md §rules" and ls[1].status.startswith("applied 2026-12-01")
    assert pending_market(path) == []
    with pytest.raises(ValueError):
        set_status("2026-01-01", "planner", "x", path)
