import pytest

from src.events import build, flag_for, fresh_flag, in_window, parse_event, save_events, window_end

D = "2026-09-14"


def test_window_end_is_calendar_days():
    assert window_end(D, 5) == "2026-09-19"


def test_flag_rules():
    assert flag_for([], D, 5) == "go"
    assert flag_for([{"date": "2026-09-18", "severity": "minor"}], D, 5) == "caution"
    assert flag_for([{"date": "2026-09-18", "severity": "major"}], D, 5) == "no-trade"
    assert flag_for([{"date": "2026-09-20", "severity": "major"}], D, 5) == "go"  # outside window
    assert flag_for([{"date": "2026-09-14", "severity": "major"}], D, 5) == "no-trade"  # today counts


def test_build_validates_and_sorts():
    d = build([{"date": "2026-09-18", "name": "b", "severity": "minor"}, {"date": "2026-09-15", "name": "a", "severity": "minor"}], D, 5)
    assert [e["name"] for e in d["events"]] == ["a", "b"] and d["flag"] == "caution" and d["window_end"] == "2026-09-19"
    with pytest.raises(ValueError):
        build([{"date": "2026-09-18", "name": "x", "severity": "huge"}], D, 5)
    with pytest.raises(ValueError):
        build([{"date": "not a date", "name": "x", "severity": "minor"}], D, 5)


def test_parse_event():
    assert parse_event("2026-09-17 | FOMC | major") == {"date": "2026-09-17", "name": "FOMC", "severity": "major"}
    with pytest.raises(ValueError):
        parse_event("2026-09-17 FOMC")


def test_fresh_flag_and_window(tmp_path):
    path = tmp_path / "events.json"
    assert fresh_flag(D, path) == (None, None)
    save_events(build([{"date": "2026-09-16", "name": "CPI", "severity": "major"}], D, 5), path)
    flag, data = fresh_flag(D, path)
    assert flag == "no-trade" and in_window(data, "2026-09-15")[0]["name"] == "CPI"
    assert fresh_flag("2026-09-15", path)[0] is None  # yesterday's scouting is stale
    assert in_window(data, "2026-09-17") == []
