"""Phase 7D: fail-closed PAPER automated-entry risk assessment.

Pure observation only: no orders, writes, or broker connections.
The caller must recheck under the authoritative state lock if execution is
ever introduced. An eligible assessment is never execution authorization.
"""
from datetime import datetime, timezone
from decimal import Decimal

from app import postgres_auto_controller as controller
from app import postgres_positions as positions

COOLDOWN_SECONDS = 120


def assess(state, accounting, *, proposal, automation_enabled=False, now=None):
    now = now or datetime.now(timezone.utc)
    if not isinstance(now, datetime) or now.tzinfo is None:
        raise ValueError("An aware timestamp is required")
    now = now.astimezone(timezone.utc)
    gate = controller.evaluate(
        state, accounting, automation_enabled=automation_enabled, now=now)
    reasons = list(gate["reasons"])
    assessment = None
    if not isinstance(proposal, dict):
        reasons.append("INVALID_PROPOSAL")
    else:
        try:
            # Preview-only copy: do not change authoritative engine state.
            # The operational gate still blocks paused execution.
            preview_state = dict(state)
            preview_state["paused"] = False
            assessment = positions.validate_open(
                preview_state, pair=proposal["pair"], side=proposal["side"],
                units=proposal["units"], entry_price=proposal["entry_price"],
                stop_loss=proposal["stop_loss"])
        except (KeyError, TypeError, ValueError, positions.RiskRejected):
            reasons.append("POSITION_RISK_REJECTED")
    # Automated limits are stricter than manual PAPER position limits.
    if assessment is not None:
        try:
            if positions.number(assessment["notional_usd"]) > controller.MAX_AUTOMATED_EXPOSURE_USD:
                reasons.append("AUTOMATION_EXPOSURE_LIMIT")
            existing = state["positions"]
            exposure = sum(
                (positions.number(p["entry_price"]) * int(p["units"])
                 for p in existing), Decimal("0"))
            if exposure + positions.number(assessment["notional_usd"]) > controller.MAX_AUTOMATED_EXPOSURE_USD:
                reasons.append("AUTOMATION_EXPOSURE_LIMIT")
            if len(existing) + 1 > controller.MAX_AUTOMATED_POSITIONS:
                reasons.append("AUTOMATION_POSITION_LIMIT")
        except (KeyError, TypeError, ValueError, positions.RiskRejected):
            reasons.append("INVALID_STATE")
    last = state.get("last_automated_entry_at")
    if last is not None:
        try:
            timestamp = datetime.fromisoformat(last)
            if timestamp.tzinfo is None:
                raise ValueError("Naive timestamp")
            elapsed = (now - timestamp.astimezone(timezone.utc)).total_seconds()
            if elapsed < COOLDOWN_SECONDS:
                reasons.append("AUTOMATION_COOLDOWN")
        except (TypeError, ValueError, OverflowError):
            reasons.append("INVALID_COOLDOWN_TIMESTAMP")
    # Even with no reasons, execution is disabled by design.
    reasons = list(dict.fromkeys(reasons))
    return {
        "mode": "PAPER", "phase": "7D", "execution": "OBSERVATION_ONLY",
        "eligible": not reasons, "reasons": reasons,
        "checked_at": now.isoformat(),
        "cooldown_seconds": COOLDOWN_SECONDS,
        "assessment": assessment,
    }
