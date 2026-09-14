"""Pre-trade checklist + exact order parameters for Kraken Pro. Pure."""
from __future__ import annotations

from src.market_data import PERP_SYMBOLS
from src.sizing import loss_if_stopped

RISK_TOLERANCE = 0.02


def order_params(t: dict) -> dict:
    """What to type into the Kraken Pro perpetual order ticket."""
    long = t["direction"] == "long"
    worst = max(t["entry_zone"]) if long else min(t["entry_zone"])
    return {
        "market": PERP_SYMBOLS[t["pair"]],
        "side": "buy" if long else "sell",
        "order_type": "limit",
        "limit_price": worst,
        "entry_zone": t["entry_zone"],
        "size": t["position_qty"],
        "size_unit": t["pair"],
        "stop_loss": {"type": "stop", "trigger_price": t["stop"], "reduce_only": True},
        "take_profit": {"type": "take_profit", "trigger_price": t["target"], "reduce_only": True},
        "time_in_force": "GTC",
        "post_only": True,
    }


def run_checklist(t: dict, account_state: dict, open_positions: list, settings: dict, today: str) -> dict:
    """Each item is (name, ok, detail). go is True only when every item passes."""
    items = []

    def item(name, ok, detail=""):
        items.append({"check": name, "ok": bool(ok), "detail": detail})

    item("guardian verdict is allow", t.get("guardian_verdict") == "allow", str(t.get("guardian_verdict")))
    item("ticket status is planned", t.get("status") == "planned", str(t.get("status")))
    item("ticket dated today", t.get("id", "").startswith(today), f"{t.get('id', '')[:10]} vs {today}")
    item("stop and target set before entry", t.get("stop") is not None and t.get("target") is not None)
    item("events flag is not no-trade", t.get("events_flag") != "no-trade", str(t.get("events_flag")))
    item(f"reward-to-risk ≥ {settings.get('min_rr', 2.0)}", (t.get("rr") or 0) >= settings.get("min_rr", 2.0), f"rr {t.get('rr')}")

    max_risk = account_state["starting_balance"] * settings.get("max_risk_pct", 0.01)
    item("risk within 1% cap", (t.get("risk_usd") or 0) <= max_risk, f"${t.get('risk_usd')} of ${max_risk:.2f}")
    remaining = account_state["daily_loss_cap"] + account_state.get("realized_pnl_today", 0)
    item("risk within remaining daily budget", (t.get("risk_usd") or 0) <= remaining, f"${remaining:.2f} left")

    if t.get("entry_zone") and t.get("stop") is not None and t.get("position_qty"):
        worst = max(t["entry_zone"]) if t["direction"] == "long" else min(t["entry_zone"])
        actual = loss_if_stopped(worst, t["stop"], t["position_qty"])
        ok = abs(actual - t["risk_usd"]) <= t["risk_usd"] * RISK_TOLERANCE
        item("loss-if-stopped equals planned risk", ok, f"${actual:.2f} vs ${t['risk_usd']:.2f}")
    else:
        item("loss-if-stopped equals planned risk", False, "cannot compute")

    item("leverage within cap", (t.get("leverage_effective") or 0) <= settings.get("leverage_cap", 5), f"{t.get('leverage_effective')}x")
    item("no other open position", len(open_positions) == 0, f"{len(open_positions)} open")
    item("no losses limit hit today", account_state.get("losses_today", 0) < settings.get("max_losses_per_day", 2), f"{account_state.get('losses_today', 0)} losses today")

    go = all(i["ok"] for i in items)
    return {"go": go, "items": items, "order_params": order_params(t) if go else None}


def render(result: dict) -> str:
    lines = ["PRE-TRADE CHECKLIST"]
    for i in result["items"]:
        lines.append(f"  [{'x' if i['ok'] else ' '}] {i['check']}" + (f"  — {i['detail']}" if i["detail"] else ""))
    if result["go"]:
        p = result["order_params"]
        lines += [
            "  VERDICT: GO",
            "ORDER PARAMETERS (Kraken Pro perpetual — you place it, nothing here sends orders)",
            f"  market       : {p['market']}",
            f"  side / type  : {p['side'].upper()} {p['order_type']} @ {p['limit_price']}   (zone {p['entry_zone'][0]} – {p['entry_zone'][1]})",
            f"  size         : {p['size']} {p['size_unit']}",
            f"  stop loss    : {p['stop_loss']['trigger_price']}  (reduce-only)",
            f"  take profit  : {p['take_profit']['trigger_price']}  (reduce-only)",
            f"  tif          : {p['time_in_force']}, post-only",
        ]
    else:
        failed = [i["check"] for i in result["items"] if not i["ok"]]
        lines.append(f"  VERDICT: NO-GO — {'; '.join(failed)}")
    return "\n".join(lines)
