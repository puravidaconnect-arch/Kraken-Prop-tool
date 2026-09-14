"""`python -m src.plan BTC` — the deterministic half of /plan.

guardian pre-check → market_data → analyst → planner → guardian → print + save.
Any block or no-trade prints one line and stops. Exit codes: 0 ticket saved,
2 no trade / blocked, 1 market data failure."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date as _date

from src import journal
from src.analyst import analyse
from src.guardian import can_trade_today, check_ticket
from src.market_data import MarketDataError, get_market
from src.planner import NoTrade, build_ticket
from src.sizing import loss_if_stopped
from src.state import load_account_state, load_open_positions, load_settings

EVENTS_FLAGS = ("go", "caution", "no-trade")


def readable(t: dict, note: str, funding: dict) -> str:
    worst = max(t["entry_zone"]) if t["direction"] == "long" else min(t["entry_zone"])
    lines = [
        f"TRADE TICKET  {t['id']}",
        f"  {t['pair']} {t['direction'].upper()}  ·  {t['strategy']}  ·  daily {t['market_class']['daily']} / weekly {t['market_class']['weekly']}",
        f"  setup      : {note}",
        f"  entry zone : {t['entry_zone'][0]} – {t['entry_zone'][1]}  (sized at worst case {worst})",
        f"  stop       : {t['stop']}   ({t['stop_distance_pct']:.2f}% · {t['stop_distance_atr']} ATR)",
        f"  target     : {t['target']}   (R:R {t['rr']:.2f})",
        f"  risk       : ${t['risk_usd']:.2f}  →  position ${t['position_usd']:,.2f}  =  {t['position_qty']} {t['pair']}  ({t['leverage_effective']:.3f}x)",
        f"  loss if stopped: ${loss_if_stopped(worst, t['stop'], t['position_qty']):.2f}",
        f"  funding    : {t['funding_rate']}  (mark {funding.get('mark_price')})",
        f"  events     : {t['events_flag']}    guardian: {t['guardian_verdict']}",
    ]
    return "\n".join(lines)


def market_read_lines(pair: str, analysis: dict) -> str:
    d, w = analysis["daily"], analysis["weekly"]
    lv = d["levels"]
    return "\n".join([
        f"MARKET READ  {pair}  (last completed daily bar {lv.get('last_bar_time', '?')[:10]})",
        f"  daily  : {d['market_class']}  — {d['reasons'][0]}",
        f"  weekly : {w['market_class']}  — {w['reasons'][0]}",
        f"  close {lv['close']:.2f} · 50 EMA {lv['ema50']} · 200 EMA {lv['ema200']} · ATR14 {lv['atr14']} ({lv['atr14_pct']}%) · RSI {lv['rsi14']}",
        f"  swing highs {lv['swing_highs']}  swing lows {lv['swing_lows']}",
        f"  60-bar band {lv['band_low']} – {lv['band_high']}  (touches {lv['band_low_touches']} low / {lv['band_high_touches']} high)",
    ])


def run(pair: str, events_flag: str = "go", date: str | None = None, save: bool = True,
        market_getter=get_market, out=sys.stdout, journal_dir=None) -> int:
    settings, acct, open_pos = load_settings(), load_account_state(), load_open_positions()
    date = date or _date.today().isoformat()

    pre = can_trade_today(acct, open_pos, settings)
    if not pre.allow:
        print(f"NO TRADE TODAY (guardian): {'; '.join(pre.reasons)}", file=out)
        return 2
    if pair not in settings["instruments"]:
        print(f"BLOCKED (guardian): instrument {pair!r} not allowed", file=out)
        return 2

    try:
        md = market_getter(pair)
    except MarketDataError as exc:
        print(f"MARKET DATA FAILED: {exc}. Stopping — no ticket without live data.", file=out)
        return 1

    analysis = analyse(md.daily, md.weekly)
    print(market_read_lines(pair, analysis), file=out)
    if events_flag != "go":
        print(f"  events_scout flag: {events_flag}", file=out)

    try:
        ticket = build_ticket(pair, date, analysis, acct, settings, md.funding["funding_rate"], events_flag)
    except NoTrade as exc:
        print(f"NO TRADE: {exc}", file=out)
        return 2

    verdict = check_ticket(ticket, acct, open_pos, settings)
    ticket["guardian_verdict"] = verdict.verdict
    if not verdict.allow:
        print(f"BLOCKED (guardian): {'; '.join(verdict.reasons)}", file=out)
        return 2

    note = ticket.pop("_planner_note", "")
    print("", file=out)
    print(readable(ticket, note, md.funding), file=out)
    print("", file=out)
    print(json.dumps(ticket, indent=2), file=out)
    if save:
        path = journal.save_ticket(ticket, journal_dir or journal.JOURNAL_DIR)
        print(f"\nsaved {path.parent.name}/{path.name}  (status: planned)", file=out)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Build a trade ticket from live Kraken data.")
    ap.add_argument("pair", help="BTC or ETH")
    ap.add_argument("--events-flag", choices=EVENTS_FLAGS, default="go",
                    help="verdict from events_scout (default go; events_scout arrives in Phase 3)")
    ap.add_argument("--date", help="ticket date YYYY-MM-DD (default today)")
    ap.add_argument("--no-save", action="store_true", help="print only, do not write journal/")
    args = ap.parse_args(argv)
    return run(args.pair.upper(), args.events_flag, args.date, save=not args.no_save)


if __name__ == "__main__":
    sys.exit(main())
