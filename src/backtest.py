"""Walk-forward backtest of analyst + planner on daily OHLCV. Used to test
market lessons before they become rules (CLAUDE.md §7) and by evals.

  python -m src.backtest evals/charts/BTC_daily.csv --set stop_buffer_atr=0.5 --set min_stop_atr=1.0
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field, asdict

import pandas as pd

from src.analyst import DEFAULT_PARAMS, analyse
from src.market_data import load_ohlc_csv
from src.planner import PLANNER_PARAMS, NoTrade, build_ticket

MIN_YEARS = 2
BARS_PER_YEAR = 365
ACCOUNT = {"starting_balance": 5000, "current_balance": 5000}
SETTINGS = {"instruments": ["BTC", "ETH", "XRP"], "risk_pct": 0.005, "min_rr": 2.0, "leverage_cap": 5}


@dataclass
class Trade:
    signal_bar: int
    direction: str
    entry: float
    stop: float
    target: float
    fill_bar: int | None = None
    exit_bar: int | None = None
    outcome: str | None = None  # target_hit | stop_hit | unfilled | timed_out
    r: float = 0.0


@dataclass
class Result:
    n_signals: int
    n_filled: int
    wins: int
    losses: int
    expectancy_r: float
    win_rate: float
    max_drawdown_r: float
    total_r: float
    trades: list[Trade] = field(default_factory=list)

    def summary(self) -> dict:
        return {k: v for k, v in asdict(self).items() if k != "trades"}


def to_weekly(daily: pd.DataFrame) -> pd.DataFrame:
    w = daily.set_index("time").resample("W").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
    return w.reset_index()


def simulate(bars: pd.DataFrame, direction: str, zone: list, stop: float, target: float,
             fill_window: int = 5, max_hold: int = 30) -> tuple[str, int | None, int | None, float]:
    """Fill when price trades into the zone within fill_window bars, then first
    touch of stop/target decides (stop first if both in one bar). Returns
    (outcome, fill_offset, exit_offset, r_multiple)."""
    long = direction == "long"
    worst = max(zone) if long else min(zone)
    risk = abs(worst - stop)
    fill = None
    for i in range(min(fill_window, len(bars))):
        b = bars.iloc[i]
        if (b["low"] <= worst) if long else (b["high"] >= worst):
            fill = i
            break
    if fill is None:
        return "unfilled", None, None, 0.0
    for j in range(fill, min(fill + max_hold, len(bars))):
        b = bars.iloc[j]
        if (b["low"] <= stop) if long else (b["high"] >= stop):
            return "stop_hit", fill, j, -1.0
        if (b["high"] >= target) if long else (b["low"] <= target):
            return "target_hit", fill, j, abs(target - worst) / risk
    last = bars.iloc[min(fill + max_hold, len(bars)) - 1]["close"]
    return "timed_out", fill, min(fill + max_hold, len(bars)) - 1, ((last - worst) if long else (worst - last)) / risk


def run(daily: pd.DataFrame, analyst_params: dict = DEFAULT_PARAMS, planner_params: dict = PLANNER_PARAMS,
        pair: str = "BTC", step: int = 1, require_years: float = MIN_YEARS) -> Result:
    if len(daily) < require_years * BARS_PER_YEAR:
        raise ValueError(f"need ≥ {require_years} years of daily bars ({require_years * BARS_PER_YEAR}), got {len(daily)}")
    weekly_all = to_weekly(daily)
    trades: list[Trade] = []
    busy_until = -1
    start = analyst_params["min_bars"]
    for i in range(start, len(daily) - 1, step):
        if i <= busy_until:
            continue
        hist = daily.iloc[: i + 1]
        cutoff = hist["time"].iloc[-1]
        weekly = weekly_all[weekly_all["time"] <= cutoff]
        try:
            analysis = analyse(hist, weekly, analyst_params)
            t = build_ticket(pair, str(cutoff.date()), analysis, ACCOUNT, SETTINGS, None, "go", planner_params)
        except (NoTrade, KeyError, ValueError):
            continue
        outcome, f, e, r = simulate(daily.iloc[i + 1 :], t["direction"], t["entry_zone"], t["stop"], t["target"])
        r = round(float(r), 3)
        tr = Trade(i, t["direction"], max(t["entry_zone"]) if t["direction"] == "long" else min(t["entry_zone"]),
                   t["stop"], t["target"], f, e, outcome, r)
        trades.append(tr)
        if e is not None:
            busy_until = i + 1 + e  # one position at a time
        elif f is None:
            busy_until = i + 5      # resting order window
    filled = [t for t in trades if t.outcome != "unfilled"]
    rs = [t.r for t in filled]
    wins, losses = sum(1 for r in rs if r > 0), sum(1 for r in rs if r < 0)
    equity, peak, mdd = 0.0, 0.0, 0.0
    for r in rs:
        equity += r
        peak = max(peak, equity)
        mdd = max(mdd, peak - equity)
    return Result(len(trades), len(filled), wins, losses,
                  round(float(sum(rs)) / len(rs), 3) if rs else 0.0,
                  round(wins / len(rs), 3) if rs else 0.0, round(float(mdd), 2), round(float(sum(rs)), 2), trades)


def improved(baseline: Result, candidate: Result, min_trades: int = 10) -> tuple[bool, str]:
    """Candidate wins only with enough trades, higher expectancy and no worse drawdown."""
    if candidate.n_filled < min_trades:
        return False, f"candidate has only {candidate.n_filled} filled trades (< {min_trades})"
    if candidate.expectancy_r <= baseline.expectancy_r:
        return False, f"expectancy {candidate.expectancy_r}R ≤ baseline {baseline.expectancy_r}R"
    if candidate.max_drawdown_r > baseline.max_drawdown_r * 1.1:
        return False, f"max drawdown {candidate.max_drawdown_r}R worse than baseline {baseline.max_drawdown_r}R"
    return True, f"expectancy {baseline.expectancy_r}R → {candidate.expectancy_r}R, drawdown {baseline.max_drawdown_r}R → {candidate.max_drawdown_r}R"


def compare(daily: pd.DataFrame, overrides: dict, pair: str = "BTC") -> dict:
    """Baseline params vs baseline + overrides (keys may belong to either param set)."""
    ap = {**DEFAULT_PARAMS, **{k: v for k, v in overrides.items() if k in DEFAULT_PARAMS}}
    pp = {**PLANNER_PARAMS, **{k: v for k, v in overrides.items() if k in PLANNER_PARAMS}}
    unknown = set(overrides) - set(DEFAULT_PARAMS) - set(PLANNER_PARAMS)
    if unknown:
        raise ValueError(f"unknown parameters {sorted(unknown)}")
    base, cand = run(daily, DEFAULT_PARAMS, PLANNER_PARAMS, pair), run(daily, ap, pp, pair)
    ok, why = improved(base, cand)
    return {"baseline": base.summary(), "candidate": cand.summary(), "overrides": overrides, "improved": ok, "why": why}


def _parse_set(items: list[str]) -> dict:
    out = {}
    for item in items:
        k, v = item.split("=", 1)
        out[k.strip()] = float(v) if "." in v or "e" in v.lower() else int(v)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Walk-forward backtest; compare a candidate rule to the baseline.")
    ap.add_argument("csv", help="daily OHLCV CSV (≥ 2 years)")
    ap.add_argument("--pair", default="BTC")
    ap.add_argument("--set", action="append", default=[], help="param=value override (repeatable)")
    args = ap.parse_args(argv)
    daily = load_ohlc_csv(args.csv)
    try:
        return _report(daily, args)
    except ValueError as exc:
        print(f"BACKTEST REFUSED: {exc}")
        return 2


def _report(daily, args) -> int:
    if args.set:
        r = compare(daily, _parse_set(args.set), args.pair)
        print(f"baseline : {r['baseline']}")
        print(f"candidate: {r['candidate']}")
        print(f"IMPROVED: {r['improved']} — {r['why']}")
    else:
        print(run(daily, pair=args.pair).summary())
    return 0


if __name__ == "__main__":
    sys.exit(main())
