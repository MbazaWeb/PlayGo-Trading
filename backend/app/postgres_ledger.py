"""Atomic PostgreSQL paper-trading state persistence.

Requires the playgo_private schema. This is not wired into FastAPI until the
remaining MongoDB-backed accounting/order routes are converted and tested.
"""
from copy import deepcopy
from datetime import datetime, timezone
import json

STATE_ID = "paper-trading-state"
COLLECTION = "app_state"


class StaleStateError(RuntimeError):
    """Another writer has committed a newer paper account revision."""


def closed_trade_events(previous: dict, current: dict) -> list[dict]:
    """Return newly closed trades only, keyed for idempotency."""
    old_ids = {t["id"] for t in previous.get("trades", [])}
    events = []
    seen = set()
    for trade in current.get("trades", []):
        trade_id = trade["id"]
        if trade_id in old_ids or trade_id in seen:
            continue
        seen.add(trade_id)
        events.append({
            "event_id": "CLOSED:" + trade_id,
            "trade_id": trade_id,
            "event_type": "PAPER_TRADE_CLOSED",
            "payload": {"trade": deepcopy(trade)},
        })
    return events


def load_or_initialize(conn, initial: dict) -> dict:
    """Initialize a paper-only account once; never reset an existing account."""
    candidate = deepcopy(initial)
    candidate["revision"] = 0
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute(
                """insert into playgo_private.documents
                   (collection_name, document_id, body, revision)
                   values (%s, %s, %s::jsonb, 0)
                   on conflict (collection_name, document_id) do nothing""",
                (COLLECTION, STATE_ID, json.dumps(candidate)),
            )
            cur.execute(
                """select body, revision from playgo_private.documents
                   where collection_name=%s and document_id=%s""",
                (COLLECTION, STATE_ID),
            )
            row = cur.fetchone()
    if row is None:
        raise RuntimeError("Paper account unavailable")
    state = row[0] if isinstance(row[0], dict) else json.loads(row[0])
    state["revision"] = int(row[1])
    return state


def commit_state(conn, previous: dict, current: dict) -> int:
    """CAS state update and append-only trade events in one SQL transaction.

    On a stale revision or duplicate event, the transaction rolls back fully.
    The caller must restore its in-memory state on failure.
    """
    old_revision = int(previous.get("revision", 0))
    new_revision = old_revision + 1
    updated = deepcopy(current)
    updated["revision"] = new_revision
    events = closed_trade_events(previous, current)
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute(
                """update playgo_private.documents
                   set body=%s::jsonb, revision=%s, updated_at=now()
                   where collection_name=%s and document_id=%s
                     and revision=%s returning revision""",
                (json.dumps(updated), new_revision, COLLECTION, STATE_ID, old_revision),
            )
            if cur.fetchone() is None:
                raise StaleStateError("Paper account revision changed")
            for event in events:
                cur.execute(
                    """insert into playgo_private.trade_events
                       (event_id, trade_id, event_type, payload)
                       values (%s, %s, %s, %s::jsonb)""",
                    (event["event_id"], event["trade_id"], event["event_type"],
                     json.dumps(event["payload"])),
                )
    return new_revision


def recent_events(conn, limit: int = 50) -> list[dict]:
    if type(limit) is not int or not 1 <= limit <= 200:
        raise ValueError("Invalid event limit")
    with conn.cursor() as cur:
        cur.execute(
            """select event_id, trade_id, event_type, payload, recorded_at
               from playgo_private.trade_events
               where event_type='PAPER_TRADE_CLOSED'
               order by recorded_at desc, event_id desc limit %s""",
            (limit,),
        )
        rows = cur.fetchall()
    return [
        {"_id": event_id, "trade_id": trade_id, "event_type": event_type,
         "trade": (payload if isinstance(payload, dict) else json.loads(payload))["trade"],
         "recorded_at": recorded_at.isoformat() if isinstance(recorded_at, datetime) else str(recorded_at)}
        for event_id, trade_id, event_type, payload, recorded_at in rows
    ]
