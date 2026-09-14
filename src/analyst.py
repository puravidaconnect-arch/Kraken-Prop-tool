"""Deterministic market classification (CLAUDE.md §4 rules). The analyst
agent calls this and adds judgment on top; it never re-derives the rules."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict

import pandas as pd

from src.indicators import (atr, count_higher, count_lower, declining_count, ema,
                            range_bands, range_contracting, rsi, slope_pct, swing_points)

CLASSES = ("uptrend", "downtrend", "ranging", "coiling", "unclassified")

DEFAULT_PARAMS = {
    "ema_fast": 50,
    "ema_slow": 200,
    "slope_bars": 10,
    "flat_slope_atr": 0.5,      # |50 EMA change over slope_bars| below this many ATR is "flat"
    "swing_n": 3,               # bars each side for a fractal swing
    "trend_lookback": 40,
    "min_higher_lows": 2,
    "range_lookback": 60,
    "band_tol_frac": 0.10,
    "min_band_touches": 2,
    "atr_period": 14,
    "coil_bars": 10,
    "coil_min_declines": 8,     # ATR must fall in at least this many of the last coil_bars steps
    "min_bars": 210,
}

STRATEGY = {"uptrend": "trend_pullback", "downtrend": "trend_pullback", "ranging": "range_fade",
            "coiling": None, "unclassified": None}


@dataclass
class MarketRead:
    market_class: str
    reasons: list[str] = field(default_factory=list)
    levels: dict = field(default_factory=dict)
    evidence: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return asdict(self)


def compute_levels(df: pd.DataFrame, p: dict = DEFAULT_PARAMS) -> dict:
    """Numbers the planner and the morning report need, from completed bars."""
    e50, e200, a, r = ema(df["close"], p["ema_fast"]), ema(df["close"], p["ema_slow"]), atr(df, p["atr_period"]), rsi(df["close"])
    sh, sl = swing_points(df, p["swing_n"])
    bands = range_bands(df, p["swing_n"], p["range_lookback"], p["band_tol_frac"])
    return {
        "close": float(df["close"].iloc[-1]),
        "last_bar_time": df["time"].iloc[-1].isoformat() if "time" in df else None,
        "ema50": round(float(e50.iloc[-1]), 2),
        "ema200": round(float(e200.iloc[-1]), 2),
        "ema50_slope_pct": round(slope_pct(e50, p["slope_bars"]), 3),
        "atr14": round(float(a.iloc[-1]), 2),
        "atr14_pct": round(float(a.iloc[-1]) / float(df["close"].iloc[-1]) * 100, 3),
        "rsi14": round(float(r.iloc[-1]), 1),
        "swing_highs": [round(v, 2) for v in sh.iloc[-5:]],
        "swing_lows": [round(v, 2) for v in sl.iloc[-5:]],
        "last_swing_high": round(float(sh.iloc[-1]), 2) if len(sh) else None,
        "last_swing_low": round(float(sl.iloc[-1]), 2) if len(sl) else None,
        "band_high": round(bands["high"], 2),
        "band_low": round(bands["low"], 2),
        "band_high_touches": bands["high_touches"],
        "band_low_touches": bands["low_touches"],
        "band_height_pct": round(bands["height_pct"], 2),
    }


def classify(df: pd.DataFrame, p: dict = DEFAULT_PARAMS) -> MarketRead:
    """Apply the §4 rules in order: uptrend, downtrend, coiling, ranging, else unclassified."""
    if len(df) < p["min_bars"]:
        return MarketRead("unclassified", [f"only {len(df)} bars, need {p['min_bars']}"])

    lv = compute_levels(df, p)
    close, e50, e200, slope = lv["close"], lv["ema50"], lv["ema200"], lv["ema50_slope_pct"]
    _, sl = swing_points(df.iloc[-p["trend_lookback"]:], p["swing_n"])
    sh, _ = swing_points(df.iloc[-p["trend_lookback"]:], p["swing_n"])
    higher_lows, lower_highs = count_higher(sl), count_lower(sh)
    a = atr(df, p["atr_period"])
    atr_declines = declining_count(a, p["coil_bars"])
    contracting = range_contracting(df, p["coil_bars"])
    ev = {
        "close_vs_ema50": "above" if close > e50 else "below",
        "ema50_vs_ema200": "above" if e50 > e200 else "below",
        "ema50_slope_pct": slope,
        "higher_lows_40": higher_lows,
        "lower_highs_40": lower_highs,
        "atr_declines_10": atr_declines,
        "range_contracting": contracting,
        "band_high_touches": lv["band_high_touches"],
        "band_low_touches": lv["band_low_touches"],
    }
    ema50_move = abs(float(ema(df["close"], p["ema_fast"]).iloc[-1]) - float(ema(df["close"], p["ema_fast"]).iloc[-1 - p["slope_bars"]]))
    flat = ema50_move < p["flat_slope_atr"] * lv["atr14"]
    ev["ema50_move_atr"] = round(ema50_move / lv["atr14"], 2)

    if close > e50 and e50 > e200 and slope > 0 and higher_lows >= p["min_higher_lows"]:
        return MarketRead("uptrend", [f"close > 50 EMA > 200 EMA, 50 EMA slope +{slope:.2f}% / {p['slope_bars']} bars, "
                                      f"{higher_lows} higher swing lows in {p['trend_lookback']} bars"], lv, ev)
    if close < e50 and e50 < e200 and slope < 0 and lower_highs >= p["min_higher_lows"]:
        return MarketRead("downtrend", [f"close < 50 EMA < 200 EMA, 50 EMA slope {slope:.2f}% / {p['slope_bars']} bars, "
                                        f"{lower_highs} lower swing highs in {p['trend_lookback']} bars"], lv, ev)
    if atr_declines >= p["coil_min_declines"] and contracting:
        return MarketRead("coiling", [f"ATR fell in {atr_declines}/{p['coil_bars']} bars and range is contracting: wait for breakout"], lv, ev)
    if flat and lv["band_high_touches"] >= p["min_band_touches"] and lv["band_low_touches"] >= p["min_band_touches"]:
        return MarketRead("ranging", [f"50 EMA slope {slope:+.2f}% (flat), band {lv['band_low']}–{lv['band_high']} touched "
                                      f"{lv['band_low_touches']}x low / {lv['band_high_touches']}x high in {p['range_lookback']} bars"], lv, ev)

    why = []
    if not (close > e50 and e50 > e200) and not (close < e50 and e50 < e200):
        why.append("EMAs not stacked for a trend")
    elif close > e50 and slope <= 0:
        why.append("50 EMA slope not positive")
    elif close < e50 and slope >= 0:
        why.append("50 EMA slope not negative")
    else:
        why.append(f"only {higher_lows} higher lows / {lower_highs} lower highs")
    if not flat:
        why.append("slope not flat enough for a range")
    else:
        why.append(f"band touches {lv['band_low_touches']} low / {lv['band_high_touches']} high (need {p['min_band_touches']})")
    return MarketRead("unclassified", ["; ".join(why)], lv, ev)


def weekly_agrees(daily_class: str, weekly_class: str) -> bool:
    """Weekly contradicts daily only when it is the opposite trend."""
    opposite = {"uptrend": "downtrend", "downtrend": "uptrend"}
    return opposite.get(daily_class) != weekly_class


def analyse(daily: pd.DataFrame, weekly: pd.DataFrame, p: dict = DEFAULT_PARAMS) -> dict:
    d, w = classify(daily, p), classify(weekly, {**p, "min_bars": p["ema_slow"] + p["slope_bars"] + 1})
    agree = weekly_agrees(d.market_class, w.market_class)
    return {
        "daily": d.as_dict(),
        "weekly": w.as_dict(),
        "market_class": {"daily": d.market_class, "weekly": w.market_class},
        "weekly_agrees": agree,
        "strategy": STRATEGY[d.market_class] if agree else None,
    }
