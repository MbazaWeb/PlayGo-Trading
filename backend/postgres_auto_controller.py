"""Phase 7A: fail-closed PAPER automation eligibility controller.

Observation-only. This module cannot open positions, place orders, or connect
to a broker. Enabling eligibility never executes a trade.
"""
from datetime import datetime, timezone
from decimal import Decimal

import postgres_positions as risk

MAX_AUTOMATED_POSITIONS = 2
MAX_AUTOMATED_EXPOSURE_USD = Decimal("5000")


def evaluate(state, accounting, *, automation_enabled=False, now=None):
    """Return an auditable decision; never mutate inputs or execute trades."""
    reasons = []
    if automation_enabled is not True:
        reasons.append("AUTOMATION_DISABLED")
    if state.get("feed_type") != "SYNTHETIC":
        reasons.append("UNSUPPORTED_FEED")
    if state.get("paused", True):
        reasons.append("ENGINE_PAUSED")
    if state.get("risk_lock_reason"):
        reasons.append("RISK_LOCKED")
    if state.get("loss_streak", 0) >= 3:
        reasons.append("LOSS_STREAK")
    today = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).date().isoformat()
    if state.get("day_start_date") != today:
        reasons.append("SESSION_ROLLOVER_REQUIRED")
    if not accounting.get("consistent", False):
        reasons.append("ACCOUNTING_INCONSISTENT")
    try:
        cash = risk.number(state["balance"])
        day_start = risk.number(state["day_start_balance"])
        ledger_cash = accounting["balances_cents"]["CASH"]
        if type(ledger_cash) is not int or cash * 100 != ledger_cash:
            reasons.append("CASH_MISMATCH")
        if day_start <= 0 or cash <= day_start * (1 - risk.DAILY_DRAWDOWN):
            reasons.append("DAILY_DRAWDOWN")
        positions = state["positions"]
        if not isinstance(positions, list):
            raise ValueError("Invalid positions")
        if len(positions) >= MAX_AUTOMATED_POSITIONS:
            reasons.append("AUTOMATION_POSITION_LIMIT")
        exposure = sum(
            (risk.number(p["entry_price"]) * int(p["units"]) for p in positions),
            Decimal("0"),
        )
        if exposure >= MAX_AUTOMATED_EXPOSURE_USD:
            reasons.append("AUTOMATION_EXPOSURE_LIMIT")
    except (KeyError, TypeError, ValueError, risk.RiskRejected):
        reasons.append("INVALID_STATE")
    return {
        "mode": "PAPER",
        "phase": "7A",
        "execution": "OBSERVATION_ONLY",
        "automation_enabled": automation_enabled is True,
        "eligible": not reasons,
        "reasons": reasons,
        "limits": {
            "max_automated_positions": MAX_AUTOMATED_POSITIONS,
            "max_automated_exposure_usd": str(MAX_AUTOMATED_EXPOSURE_USD),
        },
    }
