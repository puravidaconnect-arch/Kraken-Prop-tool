"""Guardian: rule checks as pure functions. No LLM, no I/O.

Implements config/risk_rules.md. Every function returns a Verdict; a plan
is only allowed when *every* check passes. Blocked means blocked.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from src.sizing import loss_if_stopped, reward_to_risk

VALID_DIRECTIONS = ("long", "short")
RISK_TOLERANCE = 0.02  # 2% slack between planned risk_usd and loss_if_stopped


@dataclass
class Verdict:
    allow: bool
    reasons: list[str] = field(default_factory=list)

    @property
    def verdict(self) -> str:
        return "allow" if self.allow else "block"

    def as_dict(self) -> dict:
        return {"verdict": self.verdict, "reasons": list(self.reasons)}


def _block(reasons: list[str]) -> Verdict:
    return Verdict(allow=not reasons, reasons=reasons)


def worst_case_entry(direction: str, entry_zone) -> float:
    """The entry price that gives the smallest R:R inside the zone."""
    lo, hi = min(entry_zone), max(entry_zone)
    return hi if direction == "long" else lo


# ---------------------------------------------------------------- account gates

def can_trade_today(account_state: dict, open_positions: list, settings: dict) -> Verdict:
    """Pre-check for /plan step 1: is any new trade allowed today at all?"""
    reasons: list[str] = []
    max_losses = settings.get("max_losses_per_day", 2)
    max_open = settings.get("max_open_positions", 1)

    if account_state.get("losses_today", 0) >= max_losses:
        reasons.append(f"{account_state['losses_today']} losses today: daily loss count reached")

    cap = account_state["daily_loss_cap"]
    pnl_today = account_state.get("realized_pnl_today", 0)
    if -pnl_today >= cap:
        reasons.append(f"daily loss cap ${cap:,.2f} already reached (pnl today ${pnl_today:,.2f})")

    if account_state.get("drawdown_room", 0) <= 0:
        reasons.append("no drawdown room left")

    if len(open_positions) >= max_open:
        reasons.append(f"{len(open_positions)} open position(s): max is {max_open}")

    return _block(reasons)


# ---------------------------------------------------------------- ticket checks

def check_ticket(ticket: dict, account_state: dict, open_positions: list, settings: dict) -> Verdict:
    """Validate a full trade ticket. Returns block with every reason found."""
    reasons: list[str] = list(can_trade_today(account_state, open_positions, settings).reasons)

    pair = ticket.get("pair")
    if pair not in settings["instruments"]:
        reasons.append(f"instrument {pair!r} not allowed (only {', '.join(settings['instruments'])})")

    direction = ticket.get("direction")
    if direction not in VALID_DIRECTIONS:
        reasons.append(f"direction {direction!r} must be one of {VALID_DIRECTIONS}")

    stop, target = ticket.get("stop"), ticket.get("target")
    zone = ticket.get("entry_zone")
    if stop is None:
        reasons.append("missing stop loss")
    if target is None:
        reasons.append("missing take profit target")
    if not zone or len(zone) != 2:
        reasons.append("missing or malformed entry_zone")

    # Geometry and R:R only make sense once the basics are present.
    if stop is not None and target is not None and zone and len(zone) == 2 and direction in VALID_DIRECTIONS:
        entry = worst_case_entry(direction, zone)
        lo, hi = min(zone), max(zone)
        if direction == "long" and not (stop < lo and target > hi):
            reasons.append("long geometry invalid: need stop < entry_zone < target")
        elif direction == "short" and not (stop > hi and target < lo):
            reasons.append("short geometry invalid: need target < entry_zone < stop")
        else:
            rr = reward_to_risk(entry, stop, target)
            min_rr = settings.get("min_rr", 2.0)
            if rr < min_rr:
                reasons.append(f"reward-to-risk {rr:.2f} below minimum {min_rr:.1f} (worst-case entry {entry})")

    # Risk budget checks.
    starting = account_state["starting_balance"]
    max_risk_usd = starting * settings.get("max_risk_pct", 0.01)
    risk_usd = ticket.get("risk_usd")
    if risk_usd is None:
        reasons.append("missing risk_usd")
    else:
        if risk_usd > max_risk_usd + 1e-9:
            reasons.append(f"risk ${risk_usd:,.2f} exceeds 1% cap ${max_risk_usd:,.2f}")
        remaining_daily = account_state["daily_loss_cap"] + account_state.get("realized_pnl_today", 0)
        if risk_usd > remaining_daily + 1e-9:
            reasons.append(f"risk ${risk_usd:,.2f} exceeds remaining daily budget ${remaining_daily:,.2f}")
        if risk_usd > account_state.get("drawdown_room", 0) + 1e-9:
            reasons.append(f"risk ${risk_usd:,.2f} exceeds drawdown room ${account_state.get('drawdown_room', 0):,.2f}")

        qty = ticket.get("position_qty")
        if qty is not None and stop is not None and zone and len(zone) == 2 and direction in VALID_DIRECTIONS:
            actual = loss_if_stopped(worst_case_entry(direction, zone), stop, qty)
            if actual > risk_usd * (1 + RISK_TOLERANCE):
                reasons.append(f"loss if stopped ${actual:,.2f} exceeds planned risk ${risk_usd:,.2f}")

    # Events gate.
    if ticket.get("events_flag") == "no-trade" and not ticket.get("events_override"):
        reasons.append("events_scout flagged no-trade inside hold window (no explicit override)")

    return _block(reasons)


def check_stop_update(ticket: dict, new_stop: float) -> Verdict:
    """Stops are never widened after entry. Tightening is allowed."""
    old_stop, direction = ticket["stop"], ticket["direction"]
    widened = new_stop < old_stop if direction == "long" else new_stop > old_stop
    if widened:
        return Verdict(False, [f"cannot widen stop from {old_stop} to {new_stop} on a {direction}"])
    return Verdict(True)
