"""Deterministic trade-ticket construction (CLAUDE.md §4 strategy → plan
mapping). Returns a ticket or a one-line no-trade reason. Sizing comes from
sizing.py; the guardian verdict is attached by the caller, never here."""
from __future__ import annotations

from src.journal import new_ticket
from src.sizing import SizingError, reward_to_risk, size_position

PRICE_DECIMALS = {"BTC": 0, "ETH": 1}
ZONE_HALF_WIDTH_ATR = 0.25   # entry zone is ±0.25 ATR around the level
STOP_BUFFER_ATR = 0.10       # stop sits this far beyond the structure
RANGE_STOP_ATR = 0.50        # range trades: stop this far outside the band
RANGE_PROXIMITY_ATR = 1.0    # must be within 1 ATR of a band to fade it


class NoTrade(Exception):
    """Raised with a one-line reason when no valid plan exists."""


def _r(pair: str, x: float) -> float:
    d = PRICE_DECIMALS.get(pair, 2)
    return round(x, d) if d else float(round(x))


def _trend_levels(direction: str, lv: dict) -> tuple[float, float, str]:
    """Return (entry level, structural stop, note) for a pullback trade."""
    close, e50, a = lv["close"], lv["ema50"], lv["atr14"]
    if direction == "long":
        swing_low = lv.get("last_swing_low")
        if swing_low is None:
            raise NoTrade("uptrend but no swing low to place a stop under")
        # prior swing high turned support: highest swing high below price and above the 50 EMA
        supports = [h for h in lv.get("swing_highs", []) if e50 < h < close]
        level = max(supports) if supports else e50
        note = "prior swing high turned support" if supports else "pullback to 50 EMA"
        stop = swing_low - STOP_BUFFER_ATR * a
        if stop >= level - ZONE_HALF_WIDTH_ATR * a:
            raise NoTrade(f"last swing low {swing_low} is not below the entry level {level:.0f}")
        return level, stop, note
    swing_high = lv.get("last_swing_high")
    if swing_high is None:
        raise NoTrade("downtrend but no swing high to place a stop above")
    resistances = [l for l in lv.get("swing_lows", []) if close < l < e50]
    level = min(resistances) if resistances else e50
    note = "prior swing low turned resistance" if resistances else "pullback to 50 EMA"
    stop = swing_high + STOP_BUFFER_ATR * a
    if stop <= level + ZONE_HALF_WIDTH_ATR * a:
        raise NoTrade(f"last swing high {swing_high} is not above the entry level {level:.0f}")
    return level, stop, note


def _range_levels(lv: dict) -> tuple[str, float, float, float, str]:
    """Return (direction, entry level, stop, structural target, note) for a range fade."""
    close, a, hi, lo = lv["close"], lv["atr14"], lv["band_high"], lv["band_low"]
    if abs(close - lo) <= RANGE_PROXIMITY_ATR * a:
        return "long", lo, lo - RANGE_STOP_ATR * a, hi, "buy near low band"
    if abs(close - hi) <= RANGE_PROXIMITY_ATR * a:
        return "short", hi, hi + RANGE_STOP_ATR * a, lo, "sell near high band"
    raise NoTrade(f"ranging but price {close:.0f} is mid-range (band {lo:.0f}–{hi:.0f}); wait for a band")


def build_ticket(pair: str, date: str, analysis: dict, account_state: dict, settings: dict,
                 funding_rate: float | None, events_flag: str) -> dict:
    """Build a planned ticket or raise NoTrade with the reason."""
    if pair not in settings["instruments"]:
        raise NoTrade(f"{pair} is not an allowed instrument")
    daily_class, weekly_class = analysis["market_class"]["daily"], analysis["market_class"]["weekly"]
    lv = analysis["daily"]["levels"]
    if not analysis["weekly_agrees"]:
        raise NoTrade(f"weekly {weekly_class} contradicts daily {daily_class}")
    if daily_class == "coiling":
        raise NoTrade("coiling: wait for a daily close outside the range")
    if daily_class == "unclassified":
        raise NoTrade(f"no clear market class: {analysis['daily']['reasons'][0]}")
    if events_flag == "no-trade":
        raise NoTrade("events_scout flagged no-trade inside the hold window")

    a = lv["atr14"]
    min_rr = settings.get("min_rr", 2.0)
    if daily_class in ("uptrend", "downtrend"):
        direction = "long" if daily_class == "uptrend" else "short"
        level, stop, note = _trend_levels(direction, lv)
        structural_target = None
    else:
        direction, level, stop, structural_target, note = _range_levels(lv)

    half = ZONE_HALF_WIDTH_ATR * a
    if direction == "long":
        zone = [_r(pair, level - half), _r(pair, min(level + half, lv["close"]))]
        worst = zone[1]
        target = worst + min_rr * (worst - stop)
    else:
        zone = [_r(pair, max(level - half, lv["close"])), _r(pair, level + half)]
        worst = zone[0]
        target = worst - min_rr * (stop - worst)
    stop, target = _r(pair, stop), _r(pair, target)
    if structural_target is not None:
        beyond = target > structural_target if direction == "long" else target < structural_target
        if beyond:
            raise NoTrade(f"range too narrow: {min_rr:.0f}:1 target {target} lies beyond the opposite band {structural_target}")

    try:
        sz = size_position(worst, stop, account_state["starting_balance"], settings["risk_pct"],
                           current_balance=account_state.get("current_balance"),
                           leverage_cap=settings.get("leverage_cap", 5))
    except SizingError as exc:
        raise NoTrade(f"cannot size position: {exc}") from exc

    ticket = new_ticket(
        date, pair, direction,
        strategy=analysis["strategy"],
        market_class={"daily": daily_class, "weekly": weekly_class},
        entry_zone=zone, stop=stop, target=target,
        stop_distance_pct=sz.stop_distance_pct,
        stop_distance_atr=round(abs(worst - stop) / a, 2),
        rr=round(reward_to_risk(worst, stop, target), 2),
        risk_usd=sz.risk_usd, position_usd=sz.position_usd, position_qty=sz.position_qty,
        leverage_effective=sz.leverage_effective,
        funding_rate=funding_rate, events_flag=events_flag, status="planned",
    )
    ticket["_planner_note"] = note  # readable only; stripped before saving
    return ticket
