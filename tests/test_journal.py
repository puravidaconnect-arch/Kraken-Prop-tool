import csv

import pytest

from src import journal


@pytest.fixture
def jdir(tmp_path):
    d = tmp_path / "journal"
    d.mkdir()
    return d


def test_new_ticket_has_every_field():
    t = journal.new_ticket("2026-09-14", "BTC", "long", stop=94000)
    assert t["id"] == "2026-09-14_BTC_long"
    assert set(t) == set(journal.FIELDS)
    assert t["status"] == "planned"
    assert t["stop"] == 94000
    with pytest.raises(KeyError):
        journal.new_ticket("2026-09-14", "BTC", "long", bogus=1)


def test_save_requires_guardian_verdict(jdir):
    t = journal.new_ticket("2026-09-14", "BTC", "long")
    with pytest.raises(ValueError, match="guardian verdict"):
        journal.save_ticket(t, jdir)


def test_round_trip_and_update(jdir):
    t = journal.new_ticket("2026-09-14", "BTC", "long", guardian_verdict="allow",
                           entry_zone=[99500, 100500], stop=94000, target=114000)
    path = journal.save_ticket(t, jdir)
    assert path.name == "2026-09-14_BTC_long.json"
    assert journal.load_ticket(t["id"], jdir) == t

    updated = journal.update_ticket(t["id"], jdir, status="open", fill_price=100000,
                                    opened_at="2026-09-14T14:00:00Z")
    assert updated["status"] == "open"
    assert journal.load_ticket(t["id"], jdir)["fill_price"] == 100000


def test_invalid_enums_rejected(jdir):
    t = journal.new_ticket("2026-09-14", "BTC", "long", guardian_verdict="allow")
    for bad in ({"status": "done"}, {"outcome": "won"}, {"review_tag": "meh"}):
        with pytest.raises(ValueError):
            journal.save_ticket({**t, **bad}, jdir)


def test_list_filter_closed_on_and_summary(jdir):
    a = journal.new_ticket("2026-09-10", "BTC", "long", guardian_verdict="allow", status="closed",
                           closed_at="2026-09-12T10:00:00Z", result_usd=50, outcome="target_hit",
                           followed_plan=True)
    b = journal.new_ticket("2026-09-13", "ETH", "short", guardian_verdict="allow", status="closed",
                           closed_at="2026-09-14T09:00:00Z", result_usd=-25, outcome="stop_hit",
                           followed_plan=False)
    c = journal.new_ticket("2026-09-14", "BTC", "long", guardian_verdict="allow")
    for t in (b, c, a):
        journal.save_ticket(t, jdir)

    ids = [t["id"] for t in journal.list_tickets(journal_dir=jdir)]
    assert ids == [a["id"], b["id"], c["id"]]
    assert [t["id"] for t in journal.list_tickets("planned", jdir)] == [c["id"]]
    assert [t["id"] for t in journal.tickets_closed_on("2026-09-14", jdir)] == [b["id"]]

    s = journal.summarise(journal.list_tickets(journal_dir=jdir))
    assert s["n_total"] == 3 and s["n_closed"] == 2
    assert s["n_wins"] == 1 and s["n_losses"] == 1
    assert s["win_rate"] == 0.5 and s["total_pnl_usd"] == 25
    assert s["followed_plan_rate"] == 0.5


def test_export_csv_flattens_nested_fields(jdir):
    t = journal.new_ticket("2026-09-14", "BTC", "long", guardian_verdict="allow",
                           market_class={"daily": "uptrend", "weekly": "uptrend"},
                           entry_zone=[99500, 100500], stop=94000)
    journal.save_ticket(t, jdir)
    out = journal.export_csv(jdir, jdir / "journal.csv")
    with open(out, newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 1
    r = rows[0]
    assert r["market_class_daily"] == "uptrend"
    assert r["entry_low"] == "99500" and r["entry_high"] == "100500"
    assert r["stop"] == "94000"
    assert "market_class" not in r and "entry_zone" not in r
