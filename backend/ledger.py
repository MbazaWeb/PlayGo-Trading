"""Atomic paper-state commits and append-only closed-trade ledger.

MongoDB transactions require a replica set or sharded cluster (Atlas supports
these). A failed transaction must not leave a partial ledger or state update.
"""
from datetime import datetime, timezone
from typing import Any
from pymongo.collection import Collection
from pymongo.errors import PyMongoError

STATE_ID = "paper-trading-state"


class StaleStateError(RuntimeError):
    """Another writer has changed the account; caller must reload."""


def closed_trade_events(previous: dict[str, Any], current: dict[str, Any]) -> list[dict[str, Any]]:
    old_ids = {t["id"] for t in previous.get("trades", [])}
    events = []
    for trade in current.get("trades", []):
        if trade["id"] not in old_ids:
            events.append({
                "_id": "CLOSED:" + trade["id"],
                "event_type": "PAPER_TRADE_CLOSED",
                "trade_id": trade["id"],
                "recorded_at": datetime.now(timezone.utc).isoformat(),
                "trade": dict(trade),
            })
    return events


def commit_state(state_collection: Collection, ledger_collection: Collection,
                 previous: dict[str, Any], current: dict[str, Any]) -> int:
    """Compare-and-swap account revision and append trade events in one transaction."""
    old_revision = int(previous.get("revision", 0))
    new_revision = old_revision + 1
    document = {"_id": STATE_ID, **current, "revision": new_revision}
    events = closed_trade_events(previous, current)
    client = state_collection.database.client
    with client.start_session() as session:
        with session.start_transaction():
            result = state_collection.replace_one(
                {"_id": STATE_ID, "revision": old_revision},
                document, upsert=False, session=session,
            )
            if result.matched_count != 1:
                raise StaleStateError("Account revision changed; reload before retrying")
            if events:
                ledger_collection.insert_many(events, ordered=True, session=session)
    return new_revision


def recent_events(ledger_collection: Collection, limit: int = 50) -> list[dict[str, Any]]:
    if not 1 <= limit <= 200:
        raise ValueError("Invalid event limit")
    rows = list(ledger_collection.find(
        {"event_type": "PAPER_TRADE_CLOSED"},
        {"_id": 1, "event_type": 1, "trade_id": 1, "recorded_at": 1, "trade": 1},
    ).sort("recorded_at", -1).limit(limit))
    return rows
