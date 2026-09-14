from src.checklist import order_params, render, run_checklist

D = "2026-09-14"


def test_checklist_go_and_order_params(good_ticket, account_state, settings):
    good_ticket["guardian_verdict"] = "allow"
    r = run_checklist(good_ticket, account_state, [], settings, D)
    assert r["go"], [i for i in r["items"] if not i["ok"]]
    p = r["order_params"]
    assert p["market"] == "PF_XBTUSD" and p["side"] == "buy" and p["limit_price"] == 100500
    assert p["size"] == good_ticket["position_qty"] and p["stop_loss"]["trigger_price"] == 94000
    assert p["take_profit"]["reduce_only"] is True
    text = render(r)
    assert "VERDICT: GO" in text and "you place it" in text


def test_checklist_no_go_reasons(good_ticket, account_state, settings):
    good_ticket["guardian_verdict"] = "block"
    r = run_checklist(good_ticket, account_state, [], settings, D)
    assert not r["go"] and r["order_params"] is None
    assert "guardian verdict is allow" in render(r)

    good_ticket["guardian_verdict"] = "allow"
    good_ticket["position_qty"] = 0.01  # loss if stopped $65 vs planned $25
    r = run_checklist(good_ticket, account_state, [], settings, D)
    assert [i["check"] for i in r["items"] if not i["ok"]] == ["loss-if-stopped equals planned risk"]

    good_ticket["position_qty"] = 0.00385
    r = run_checklist(good_ticket, account_state, [{"id": "x"}], settings, D)
    assert [i["check"] for i in r["items"] if not i["ok"]] == ["no other open position"]

    r = run_checklist(good_ticket, account_state, [], settings, "2026-09-15")
    assert [i["check"] for i in r["items"] if not i["ok"]] == ["ticket dated today"]


def test_short_order_params():
    t = {"pair": "ETH", "direction": "short", "entry_zone": [3000, 3050], "stop": 3200, "target": 2600, "position_qty": 0.125}
    p = order_params(t)
    assert p["side"] == "sell" and p["limit_price"] == 3000 and p["market"] == "PF_ETHUSD"
