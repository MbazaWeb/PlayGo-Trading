"""Durable, isolated demo order lifecycle. Never submits broker orders.

Each client order ID is the MongoDB _id: insert_once is protected by the
unique primary key. Recovery replays only the deterministic internal simulator.
This is a research sandbox, not a real-money execution or settlement ledger.
"""
from datetime import datetime, timezone
from hashlib import sha256
import json
from typing import Any
from pymongo.collection import Collection
from pymongo.errors import DuplicateKeyError
from demo_execution import DemoExecutionEngine, DemoOrderError

PENDING = "PENDING"
FILLED = "FILLED"
FAILED = "FAILED"


class OrderConflict(ValueError):
    pass


def fingerprint(pair: str, side: str, units: int, bid: str, ask: str) -> str:
    payload = json.dumps([pair, side, units, str(bid), str(ask)], separators=(",", ":"))
    return sha256(payload.encode("utf-8")).hexdigest()


def submit_demo_order(collection: Collection, *, client_order_id: str,
                      pair: str, side: str, units: int,
                      bid: str, ask: str,
                      slippage_pips: str = "0.2") -> dict[str, Any]:
    """Persist intent first, then settle with an atomic state transition.

    A crash between insert and fill leaves a recoverable PENDING order.
    Duplicate IDs never create a second order. Different payloads conflict.
    """
    engine = DemoExecutionEngine(slippage_pips)
    # Validate before writing an intent; computation is deterministic and offline.
    fill = engine.execute(client_order_id=client_order_id, pair=pair,
                          side=side, units=units, bid=bid, ask=ask)
    signature = fingerprint(pair, side, units, bid, ask)
    now = datetime.now(timezone.utc).isoformat()
    record = {
        "_id": client_order_id,
        "mode": "DEMO",
        "status": PENDING,
        "fingerprint": signature,
        "request": {"pair": pair, "side": side, "units": units,
                    "bid": str(bid), "ask": str(ask),
                    "slippage_pips": str(slippage_pips)},
        "created_at": now,
        "updated_at": now,
    }
    try:
        collection.insert_one(record)
    except DuplicateKeyError:
        pass
    existing = collection.find_one({"_id": client_order_id})
    if existing is None:
        raise RuntimeError("Demo intent could not be retrieved")
    if existing.get("fingerprint") != signature or existing.get("request", {}).get("slippage_pips") != str(slippage_pips):
        raise OrderConflict("Client order ID already belongs to a different request")
    if existing.get("status") == FILLED:
        return _public(existing)
    if existing.get("status") != PENDING:
        raise OrderConflict("Order is not eligible for replay")
    # Conditional update: multiple workers can compute, but only one records fill.
    collection.update_one(
        {"_id": client_order_id, "status": PENDING},
        {"$set": {"status": FILLED, "fill": fill,
                  "updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    settled = collection.find_one({"_id": client_order_id})
    if settled is None or settled.get("status") != FILLED:
        raise RuntimeError("Demo order settlement was not confirmed")
    return _public(settled)


def _public(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "client_order_id": record["_id"],
        "mode": "DEMO",
        "status": record["status"],
        "request": record["request"],
        "fill": record.get("fill"),
        "created_at": record["created_at"],
        "updated_at": record["updated_at"],
    }


def pending_orders(collection: Collection, limit: int = 100) -> list[dict[str, Any]]:
    if not 1 <= limit <= 200:
        raise ValueError("Invalid pending-order limit")
    return [_public(row) for row in collection.find(
        {"mode": "DEMO", "status": PENDING}
    ).sort("created_at", 1).limit(limit)]


def recover_pending(collection: Collection, limit: int = 100) -> dict[str, Any]:
    """Explicit, bounded offline recovery. No external orders or account mutation."""
    recovered = []
    errors = []
    for row in pending_orders(collection, limit):
        args = row["request"]
        try:
            result = submit_demo_order(collection, client_order_id=row["client_order_id"], **args)
            recovered.append(result["client_order_id"])
        except (DemoOrderError, OrderConflict, RuntimeError, KeyError, TypeError) as exc:
            errors.append({"client_order_id": row["client_order_id"], "error": type(exc).__name__})
    return {"mode": "DEMO", "recovered": recovered, "errors": errors}
