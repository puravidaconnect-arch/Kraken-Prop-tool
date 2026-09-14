"""Phase 5b acceptance: the form journals a closed trade without the terminal
and its JSON is byte-identical to what `python -m src.report close` writes."""
import http.client
import shutil
import threading
from http.server import ThreadingHTTPServer
from urllib.parse import urlencode

import pytest

from src import journal, report
from src.form import handle_action, make_handler, render_page
from src.state import Paths

TID = "2026-09-14_BTC_long"
CLOSE = {"id": TID, "fill_price": "100200", "exit_price": "94000", "position_qty": "0.00385", "result_usd": "-24.6",
         "opened_at": "2026-09-14T10:00", "closed_at": "2026-09-16T02:00", "followed_plan": "yes",
         "deviation_note": "", "mid_trade_events": "none", "emotion_note": "calm"}


@pytest.fixture
def planned(repo, good_ticket):
    good_ticket["guardian_verdict"] = "allow"
    t = journal.new_ticket("2026-09-14", "BTC", "long", **{k: v for k, v in good_ticket.items() if k in journal.FIELDS and k not in ("id", "pair", "direction")})
    journal.save_ticket(t, repo.journal)
    return t


def test_form_json_identical_to_report_cli(repo, planned, tmp_path, monkeypatch):
    # copy A: closed through the CLI; copy B: closed through the form
    cli_dir = tmp_path / "cli_journal"
    shutil.copytree(repo.journal, cli_dir)
    monkeypatch.setattr(journal, "JOURNAL_DIR", cli_dir)
    assert report.main(["close", TID, "--fill-price", "100200", "--exit-price", "94000", "--qty", "0.00385", "--result", "-24.6",
                        "--opened-at", "2026-09-14T10:00", "--closed-at", "2026-09-16T02:00", "--followed-plan", "yes",
                        "--mid-trade-events", "none", "--emotion-note", "calm"]) == 0
    ok, msg = handle_action("close", CLOSE, repo)
    assert ok, msg
    assert (repo.journal / f"{TID}.json").read_bytes() == (cli_dir / f"{TID}.json").read_bytes()
    t = journal.load_ticket(TID, repo.journal)
    assert t["status"] == "closed" and t["outcome"] == "stop_hit" and t["emotion_note"] == "calm" and t["deviation_note"] is None


def test_form_open_then_close_and_cancel(repo, planned):
    ok, msg = handle_action("open", {"id": TID, "fill_price": "100,100", "opened_at": "2026-09-14T09:30"}, repo)
    assert ok and "marked open at 100100" in msg
    ok, msg = handle_action("cancel", {"id": TID}, repo)
    assert not ok and "only a planned ticket" in msg
    ok, msg = handle_action("close", {**CLOSE, "followed_plan": "no", "deviation_note": ""}, repo)
    assert not ok and "deviation_note is required" in msg
    ok, msg = handle_action("close", {**CLOSE, "result_usd": "500"}, repo)
    assert not ok and "look wrong" in msg
    ok, msg = handle_action("close", {**CLOSE, "result_usd": "500", "force": "1"}, repo)
    assert ok and journal.load_ticket(TID, repo.journal)["result_usd"] == 500


def test_form_validation_messages(repo, planned):
    ok, msg = handle_action("close", {**CLOSE, "exit_price": ""}, repo)
    assert not ok and "exit_price is required" in msg
    ok, msg = handle_action("close", {**CLOSE, "id": "nope"}, repo)
    assert not ok and "REPORT REFUSED" in msg
    ok, msg = handle_action("dance", {"id": TID}, repo)
    assert not ok


def test_render_page_lists_pending_and_closed(repo, planned):
    page = render_page(repo)
    assert TID in page and "Close trade" in page and "Cancel plan" in page and "viewport" in page
    handle_action("close", CLOSE, repo)
    page = render_page(repo, "done")
    assert "Recently closed" in page and "stop_hit" in page and "No planned or open tickets" in page and "done" in page


def test_http_round_trip(repo, planned):
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(repo))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        c.request("GET", "/")
        r = c.getresponse()
        assert r.status == 200 and TID in r.read().decode()
        body = urlencode(CLOSE)
        c.request("POST", "/close", body=body, headers={"Content-Type": "application/x-www-form-urlencoded", "Content-Length": str(len(body))})
        r = c.getresponse()
        assert r.status == 303 and "closed" in r.getheader("Location")
        r.read()
        c.request("GET", r.getheader("Location"))
        r = c.getresponse()
        page = r.read().decode()
        assert "stop_hit" in page and "Recently closed" in page
        c.request("GET", "/nope")
        assert c.getresponse().status == 404
    finally:
        server.shutdown()
        server.server_close()
    assert journal.load_ticket(TID, repo.journal)["status"] == "closed"
