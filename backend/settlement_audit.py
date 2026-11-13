"""Read-only paper settlement coverage audit.

Detects missing and conflicting trade journal records. Never posts money.
"""
from typing import Any
from pymongo.collection import Collection
from settlement import event_to_post, SettlementError


def audit(events: Collection, journals: Collection, limit: int = 200) -> dict[str, Any]:
    if not 1 <= limit <= 1000:
        raise ValueError("Limit must be 1..1000")
    pending, mismatched, zero, settled = [], [], [], []
    rows = events.find({"event_type": "PAPER_TRADE_CLOSED"}).sort("recorded_at", -1).limit(limit)
    for row in rows:
        key = str(row.get("_id"))
        try:
            expected = event_to_post(row)
        except SettlementError:
            mismatched.append({"event_id": key, "reason": "INVALID_SOURCE_EVENT"})
            continue
        if expected is None:
            zero.append(key)
            continue
        actual = journals.find_one({"_id": expected["transaction_id"]})
        if actual is None:
            pending.append(key)
        elif (actual.get("kind"), actual.get("amount_cents"), actual.get("reference")) != (
            expected["kind"], expected["amount_cents"], expected["reference"]
        ):
            mismatched.append({"event_id": key, "reason": "JOURNAL_MISMATCH"})
        else:
            settled.append(key)
    return {"mode": "PAPER", "checked": len(pending) + len(mismatched) + len(zero) + len(settled),
            "settled": len(settled), "pending": pending, "zero_pnl": zero,
            "mismatched": mismatched, "consistent": not pending and not mismatched,
            "scope": "Most recent events only; not a full-history audit"}
