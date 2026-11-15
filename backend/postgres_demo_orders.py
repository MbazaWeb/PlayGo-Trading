"""Durable, deterministic demo orders in private Supabase PostgreSQL.

No broker API is imported or called. A transaction locks the order row to
serialize retries and recovery, and prevents conflicting idempotency keys.
"""
from datetime import datetime, timezone
import json

from demo_execution import DemoExecutionEngine, DemoOrderError
from hashlib import sha256

COLLECTION = "demo_order_intents"
PENDING = "PENDING"
FILLED = "FILLED"


class OrderConflict(ValueError):
    pass


def fingerprint(pair, side, units, bid, ask, slippage_pips):
    raw = json.dumps([pair, side, units, str(bid), str(ask), str(slippage_pips)],
                     separators=(",", ":"))
    return sha256(raw.encode()).hexdigest()


def _decode(value):
    return value if isinstance(value, dict) else json.loads(value)


def _public(record):
    return {"client_order_id": record["_id"], "mode": "DEMO",
            "status": record["status"], "request": record["request"],
            "fill": record.get("fill"), "created_at": record["created_at"],
            "updated_at": record["updated_at"]}


def submit_demo_order(conn, *, client_order_id: str, pair: str, side: str,
                      units: int, bid: str, ask: str, slippage_pips: str = "0.2"):
    # Validate and calculate a deterministic offline fill before touching SQL.
    fill = DemoExecutionEngine(slippage_pips).execute(
        client_order_id=client_order_id, pair=pair, side=side,
        units=units, bid=bid, ask=ask)
    signature = fingerprint(pair, side, units, bid, ask, slippage_pips)
    now = datetime.now(timezone.utc).isoformat()
    record = {"_id": client_order_id, "mode": "DEMO", "status": PENDING,
              "fingerprint": signature,
              "request": {"pair": pair, "side": side, "units": units,
                          "bid": str(bid), "ask": str(ask),
                          "slippage_pips": str(slippage_pips)},
              "created_at": now, "updated_at": now}
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute(
                """insert into playgo_private.documents
                   (collection_name, document_id, body, revision)
                   values (%s, %s, %s::jsonb, 0)
                   on conflict (collection_name, document_id) do nothing""",
                (COLLECTION, client_order_id, json.dumps(record)))
            cur.execute(
                """select body, revision from playgo_private.documents
                   where collection_name=%s and document_id=%s for update""",
                (COLLECTION, client_order_id))
            row = cur.fetchone()
            if row is None:
                raise RuntimeError("Demo order not persisted")
            stored = _decode(row[0])
            if stored.get("fingerprint") != signature:
                raise OrderConflict("Client order ID reused with different request")
            if stored["status"] == FILLED:
                return _public(stored)
            if stored["status"] != PENDING:
                raise OrderConflict("Order is not eligible for replay")
            stored["status"] = FILLED
            stored["fill"] = fill
            stored["updated_at"] = datetime.now(timezone.utc).isoformat()
            cur.execute(
                """update playgo_private.documents
                   set body=%s::jsonb, revision=revision+1, updated_at=now()
                   where collection_name=%s and document_id=%s""",
                (json.dumps(stored), COLLECTION, client_order_id))
            return _public(stored)


def pending_orders(conn, limit=50):
    if type(limit) is not int or not 1 <= limit <= 200:
        raise ValueError("Invalid pending-order limit")
    with conn.cursor() as cur:
        cur.execute(
            """select body from playgo_private.documents
               where collection_name=%s and body->>'status'=%s
               order by updated_at, document_id limit %s""",
            (COLLECTION, PENDING, limit))
        return [_public(_decode(row[0])) for row in cur.fetchall()]


def recover_pending(conn, limit=50):
    recovered, errors = [], []
    for row in pending_orders(conn, limit):
        try:
            submit_demo_order(conn, client_order_id=row["client_order_id"],
                              **row["request"])
            recovered.append(row["client_order_id"])
        except (DemoOrderError, OrderConflict, RuntimeError, ValueError, TypeError, KeyError) as exc:
            errors.append({"client_order_id": row["client_order_id"],
                           "error": type(exc).__name__})
    return {"mode": "DEMO", "recovered": recovered, "errors": errors}
