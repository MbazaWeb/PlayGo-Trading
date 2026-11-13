"""Reconcile and book only persisted paper trade-close events.

No broker API, live execution or external transfers. Each event is booked
using its immutable trade ID. A failed accounting post is safely retryable.
"""
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN
from typing import Any
from pymongo.collection import Collection
import accounting


class SettlementError(ValueError):
    pass


def event_to_post(event: dict[str, Any]) -> dict[str, Any] | None:
    if event.get("event_type") != "PAPER_TRADE_CLOSED":
        raise SettlementError("Unverified event type")
    trade = event.get("trade", {})
    trade_id = event.get("trade_id")
    if not trade_id or trade.get("id") != trade_id or event.get("_id") != "CLOSED:" + trade_id:
        raise SettlementError("Trade identity mismatch")
    try:
        pnl = Decimal(str(trade["pnl"]))
    except (KeyError, InvalidOperation, ValueError, TypeError) as exc:
        raise SettlementError("Invalid realized P&L") from exc
    if not pnl.is_finite():
        raise SettlementError("Non-finite realized P&L")
    cents = pnl * 100
    if cents != cents.to_integral_value():
        raise SettlementError("P&L has fractional cents")
    if cents == 0:
        return None
    if abs(cents) > 10**12:
        raise SettlementError("P&L exceeds accounting bounds")
    return {"transaction_id": "TRADE:" + trade_id,
            "kind": "REALIZED_GAIN" if cents > 0 else "REALIZED_LOSS",
            "amount_cents": int(abs(cents)), "reference": event["_id"]}


def settle_events(events: Collection, accounts: Collection, journals: Collection,
                  limit: int = 100) -> dict[str, Any]:
    if not 1 <= limit <= 200:
        raise ValueError("Invalid limit")
    processed, skipped, failures = [], [], []
    rows = events.find({"event_type": "PAPER_TRADE_CLOSED"}).sort("recorded_at", 1).limit(limit)
    for event in rows:
        event_id = str(event.get("_id"))
        try:
            entry = event_to_post(event)
            if entry is None:
                skipped.append(event_id)
                continue
            accounting.post(accounts, journals, **entry)
            processed.append(event_id)
        except (SettlementError, accounting.LedgerConflict,
                accounting.InsufficientFunds, ValueError, RuntimeError) as exc:
            failures.append({"event_id": event_id, "reason": type(exc).__name__})
    return {"mode": "PAPER", "processed_or_already_booked": processed,
            "zero_pnl_skipped": skipped, "failed": failures,
            "note": "Bounded event replay; no broker execution or money transfer."}
