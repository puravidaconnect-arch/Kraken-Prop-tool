"""Position sizing. Pure function, no I/O.

    risk_usd      = starting_balance * risk_pct
    stop_dist_pct = abs(entry - stop) / entry
    position_usd  = risk_usd / stop_dist_pct
    position_qty  = position_usd / entry
"""
from __future__ import annotations

from dataclasses import dataclass, asdict

MAX_RISK_PCT = 0.01  # hard cap from risk_rules.md


class SizingError(ValueError):
    """Raised when a position cannot be sized within the rules."""


@dataclass(frozen=True)
class Sizing:
    risk_usd: float
    stop_distance_pct: float  # as a percentage, e.g. 6.0 for 6%
    position_usd: float
    position_qty: float
    leverage_effective: float

    def as_dict(self) -> dict:
        return asdict(self)


def size_position(
    entry: float,
    stop: float,
    starting_balance: float,
    risk_pct: float,
    *,
    current_balance: float | None = None,
    leverage_cap: float = 5.0,
    qty_decimals: int = 5,
) -> Sizing:
    """Return the position size for a given entry/stop and risk budget.

    Raises SizingError if the stop equals the entry, risk_pct exceeds the
    1% cap, or the implied leverage exceeds ``leverage_cap``.
    """
    if entry <= 0 or stop <= 0:
        raise SizingError("entry and stop must be positive prices")
    if starting_balance <= 0:
        raise SizingError("starting_balance must be positive")
    if risk_pct <= 0:
        raise SizingError("risk_pct must be positive")
    if risk_pct > MAX_RISK_PCT:
        raise SizingError(f"risk_pct {risk_pct:.4f} exceeds hard cap {MAX_RISK_PCT:.2%}")

    stop_dist = abs(entry - stop) / entry
    if stop_dist == 0:
        raise SizingError("stop distance is zero: stop equals entry")

    risk_usd = starting_balance * risk_pct
    position_usd = risk_usd / stop_dist
    position_qty = round(position_usd / entry, qty_decimals)

    balance = current_balance if current_balance is not None else starting_balance
    leverage = position_usd / balance
    if leverage > leverage_cap:
        raise SizingError(
            f"implied leverage {leverage:.2f}x exceeds cap {leverage_cap:.2f}x "
            f"(position ${position_usd:,.0f} on balance ${balance:,.0f})"
        )

    return Sizing(
        risk_usd=round(risk_usd, 2),
        stop_distance_pct=round(stop_dist * 100, 4),
        position_usd=round(position_usd, 2),
        position_qty=position_qty,
        leverage_effective=round(leverage, 4),
    )


def loss_if_stopped(entry: float, stop: float, position_qty: float) -> float:
    """Dollar loss if the stop is hit at exactly the stop price."""
    return round(abs(entry - stop) * position_qty, 2)


def reward_to_risk(entry: float, stop: float, target: float) -> float:
    """R:R measured from a single entry price. Raises if stop == entry."""
    risk = abs(entry - stop)
    if risk == 0:
        raise SizingError("stop distance is zero: stop equals entry")
    return abs(target - entry) / risk
