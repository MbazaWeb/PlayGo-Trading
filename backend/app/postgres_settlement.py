"""PostgreSQL paper-trade settlement and coverage audit.

This module is staged for the FastAPI cutover; it never calls broker APIs.
"""
from decimal import Decimal, InvalidOperation
import json

from app import postgres_accounting


class SettlementError(ValueError):
    pass


def event_to_post(event: dict):
    if event.get("event_type") != "PAPER_TRADE_CLOSED":
        raise SettlementError("Unverified event type")
    trade = event.get("trade", {})
    trade_id = event.get("trade_id")
    if not isinstance(trade_id, str) or not trade_id or trade.get("id") != trade_id or event.get("_id") != "CLOSED:" + trade_id:
        raise SettlementError("Trade identity mismatch")
    try:
        pnl = Decimal(str(trade["pnl"]))
    except (KeyError, InvalidOperation, TypeError, ValueError) as exc:
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


def _events(conn, limit, descending=False):
    if type(limit) is not int or not 1 <= limit <= 1000:
        raise ValueError("Limit must be 1..1000")
    order = "desc" if descending else "asc"
    with conn.cursor() as cur:
        cur.execute(
            f"""select event_id, trade_id, event_type, payload
                from playgo_private.trade_events
                where event_type='PAPER_TRADE_CLOSED'
                order by recorded_at {order}, event_id {order} limit %s""",
            (limit,),
        )
        rows = cur.fetchall()
    for event_id, trade_id, event_type, payload in rows:
        data = payload if isinstance(payload, dict) else json.loads(payload)
        yield {"_id": event_id, "trade_id": trade_id,
               "event_type": event_type, "trade": data.get("trade", {})}


def settle_events(conn, limit=100):
    if type(limit) is not int or not 1 <= limit <= 200:
        raise ValueError("Invalid limit")
    processed, skipped, failed = [], [], []
    for event in _events(conn, limit):
        try:
            entry = event_to_post(event)
            if entry is None:
                skipped.append(event["_id"])
                continue
            postgres_accounting.post(conn, **entry)
            processed.append(event["_id"])
        except (SettlementError, ValueError, RuntimeError) as exc:
            failed.append({"event_id": event["_id"], "reason": type(exc).__name__})
    return {"mode": "PAPER", "processed_or_already_booked": processed,
            "zero_pnl_skipped": skipped, "failed": failed,
            "note": "Bounded event replay; no broker execution or money transfer."}


def audit(conn, limit=200):
    if type(limit) is not int or not 1 <= limit <= 1000:
        raise ValueError("Invalid limit")
    pending, mismatched, zero, settled = [], [], [], []
    for event in _events(conn, limit, descending=True):
        key = event["_id"]
        try:
            expected = event_to_post(event)
        except SettlementError:
            mismatched.append({"event_id": key, "reason": "INVALID_SOURCE_EVENT"})
            continue
        if expected is None:
            zero.append(key)
            continue
        with conn.cursor() as cur:
            cur.execute(
                """select kind, amount_cents, reference
                   from playgo_private.accounting_journals where transaction_id=%s""",
                (expected["transaction_id"],),
            )
            actual = cur.fetchone()
        if actual is None:
            pending.append(key)
        elif actual != (expected["kind"], expected["amount_cents"], expected["reference"]):
            mismatched.append({"event_id": key, "reason": "JOURNAL_MISMATCH"})
        else:
            settled.append(key)
    return {"mode": "PAPER", "checked": sum(map(len, (pending, mismatched, zero, settled))),
            "settled": len(settled), "pending": pending, "zero_pnl": zero,
            "mismatched": mismatched, "consistent": not pending and not mismatched,
            "scope": "Most recent events only; not a full-history audit"}
