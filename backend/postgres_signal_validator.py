"""Phase 7B: deterministic PAPER signal screening; no execution or persistence."""
from datetime import datetime, timezone
from decimal import Decimal
import re

import postgres_positions as risk

MIN_CONFIDENCE = Decimal("0.70")
MAX_SIGNAL_AGE_SECONDS = 300
MAX_FUTURE_SKEW_SECONDS = 10
MAX_SIGNAL_RISK_FRACTION = Decimal("0.005")
MAX_SIGNAL_UNITS = 1000


def validate_signal(signal, state, *, now=None, seen_ids=()):
    """Pure fail-closed signal validation. Caller owns durable deduplication."""
    reasons = []
    if not isinstance(signal, dict) or not isinstance(state, dict):
        return {"mode": "PAPER", "execution": "VALIDATION_ONLY",
                "accepted": False, "reasons": ["INVALID_INPUT"], "proposal": None}
    signal_id = signal.get("signal_id")
    if not isinstance(signal_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", signal_id):
        reasons.append("INVALID_SIGNAL_ID")
    elif signal_id in seen_ids:
        reasons.append("DUPLICATE_SIGNAL")
    pair, side = signal.get("pair"), signal.get("side")
    if pair not in risk.SUPPORTED or side not in ("BUY", "SELL"):
        reasons.append("UNSUPPORTED_SIGNAL")
    try:
        confidence = risk.number(signal.get("confidence"))
        if not Decimal("0") <= confidence <= Decimal("1") or confidence < MIN_CONFIDENCE:
            reasons.append("LOW_CONFIDENCE")
    except risk.RiskRejected:
        reasons.append("INVALID_CONFIDENCE")
    try:
        timestamp = signal["timestamp"]
        if not isinstance(timestamp, str):
            raise ValueError("timestamp must be a string")
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("timezone required")
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            raise ValueError("now requires timezone")
        age = (current - parsed).total_seconds()
        if age > MAX_SIGNAL_AGE_SECONDS or age < -MAX_FUTURE_SKEW_SECONDS:
            reasons.append("SIGNAL_EXPIRED_OR_FUTURE")
    except (KeyError, ValueError, TypeError, OverflowError):
        reasons.append("INVALID_TIMESTAMP")
    proposal = None
    if pair in risk.SUPPORTED and side in ("BUY", "SELL"):
        try:
            quote = state["quotes"][pair]
            entry = risk.number(quote["ask"] if side == "BUY" else quote["bid"])
            stop = risk.number(signal["stop_loss"])
            distance = abs(entry - stop)
            balance = risk.number(state["balance"])
            if distance <= 0 or balance <= 0:
                raise risk.RiskRejected("Invalid risk budget")
            budget = balance * MAX_SIGNAL_RISK_FRACTION
            units = min(int(budget / distance), MAX_SIGNAL_UNITS,
                        int(risk.MAX_POSITION_NOTIONAL_USD / entry))
            if units < 1:
                reasons.append("INSUFFICIENT_RISK_BUDGET")
            else:
                assessment = risk.validate_open(
                    state, pair=pair, side=side, units=units,
                    entry_price=entry, stop_loss=stop)
                proposal = {"signal_id": signal_id, "pair": pair, "side": side,
                            "units": units, "stop_loss": str(stop),
                            "assessment": assessment}
        except (KeyError, ValueError, TypeError, ZeroDivisionError, risk.RiskRejected) as exc:
            reasons.append("RISK_REJECTED")
    return {"mode": "PAPER", "execution": "VALIDATION_ONLY",
            "accepted": not reasons and proposal is not None,
            "reasons": reasons, "proposal": proposal if not reasons else None}
