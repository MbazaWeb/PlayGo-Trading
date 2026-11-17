
"""Durable, deterministic DEMO orders in private PostgreSQL.

No broker API is imported or called.

PostgreSQL provides durable idempotency using:
- Unique (collection_name, document_id) constraints
- INSERT ... ON CONFLICT DO NOTHING
- SELECT ... FOR UPDATE
- Atomic order status updates

Requires playgo_private.documents with:
    collection_name
    document_id
    body
    revision
    updated_at

Database concurrency guarantees require integration testing against
an isolated PostgreSQL database.
"""

from datetime import date, datetime, timezone
from hashlib import sha256
import json

from app.demo_execution import DemoExecutionEngine, DemoOrderError


COLLECTION = "demo_order_intents"

PENDING = "PENDING"
FILLED = "FILLED"

ALLOWED_PAIRS = frozenset(("EURUSD", "GBPUSD"))
ALLOWED_SIDES = frozenset(("BUY", "SELL"))
ALLOWED_STATUSES = frozenset((PENDING, FILLED))

MAX_ORDER_ID_LENGTH = 128


class OrderConflict(ValueError):
    """An idempotency key was reused with different order parameters."""


def fingerprint(pair, side, units, bid, ask, slippage_pips):
    """Return a deterministic fingerprint for the exact request.

    Preserve the existing serialization format for compatibility
    with previously persisted orders.
    """
    raw = json.dumps(
        [pair, side, units, str(bid), str(ask), str(slippage_pips)],
        separators=(",", ":"),
    )
    return sha256(raw.encode("utf-8")).hexdigest()


def _decode(value):
    """Decode a PostgreSQL JSONB value."""
    if isinstance(value, dict):
        return value

    if isinstance(value, (str, bytes, bytearray)):
        result = json.loads(value)
        if isinstance(result, dict):
            return result

    raise ValueError("Invalid persisted demo-order document")


def _validate_order_id(client_order_id):
    if not isinstance(client_order_id, str):
        raise ValueError("Invalid client order ID")

    if not client_order_id:
        raise ValueError("Invalid client order ID")

    if client_order_id != client_order_id.strip():
        raise ValueError("Invalid client order ID")

    if len(client_order_id) > MAX_ORDER_ID_LENGTH:
        raise ValueError("Invalid client order ID")

    if any(ord(char) < 32 or ord(char) == 127 for char in client_order_id):
        raise ValueError("Invalid client order ID")

    return client_order_id


def _validate_limit(limit, maximum):
    if type(limit) is not int or not 1 <= limit <= maximum:
        raise ValueError(
            f"Limit must be between 1 and {maximum}"
        )
    return limit


def _public(record):
    """Return the public API representation without private fingerprints."""
    return {
        "client_order_id": record["_id"],
        "mode": "DEMO",
        "status": record["status"],
        "request": record["request"],
        "fill": record.get("fill"),
        "created_at": record["created_at"],
        "updated_at": record["updated_at"],
    }


def submit_demo_order(
    conn,
    *,
    client_order_id: str,
    pair: str,
    side: str,
    units: int,
    bid: str,
    ask: str,
    slippage_pips: str = "0.2",
):
    """Submit or replay a durable, deterministic offline DEMO order.

    An identical retry returns the original persisted fill.

    A different request using the same client_order_id raises
    OrderConflict.

    The insert, row lock, and update are performed atomically.
    """
    _validate_order_id(client_order_id)

    # Validate and calculate the fill before executing SQL.
    engine = DemoExecutionEngine(slippage_pips)

    fill = engine.execute(
        client_order_id=client_order_id,
        pair=pair,
        side=side,
        units=units,
        bid=bid,
        ask=ask,
    )

    signature = fingerprint(
        pair,
        side,
        units,
        bid,
        ask,
        slippage_pips,
    )

    now = datetime.now(timezone.utc).isoformat()

    record = {
        "_id": client_order_id,
        "mode": "DEMO",
        "status": PENDING,
        "fingerprint": signature,
        "request": {
            "pair": pair,
            "side": side,
            "units": units,
            "bid": str(bid),
            "ask": str(ask),
            "slippage_pips": str(slippage_pips),
        },
        "created_at": now,
        "updated_at": now,
    }

    with conn.transaction():
        with conn.cursor() as cur:

            cur.execute(
                """
                INSERT INTO playgo_private.documents
                    (collection_name, document_id, body, revision)
                VALUES (%s, %s, %s::jsonb, 0)
                ON CONFLICT (collection_name, document_id)
                DO NOTHING
                """,
                (
                    COLLECTION,
                    client_order_id,
                    json.dumps(record),
                ),
            )

            cur.execute(
                """
                SELECT body, revision
                FROM playgo_private.documents
                WHERE collection_name = %s
                  AND document_id = %s
                FOR UPDATE
                """,
                (COLLECTION, client_order_id),
            )

            row = cur.fetchone()

            if row is None:
                raise RuntimeError(
                    "Demo order was not persisted"
                )

            stored = _decode(row[0])

            if stored.get("fingerprint") != signature:
                raise OrderConflict(
                    "Client order ID reused with different request"
                )

            status = stored.get("status")

            if status == FILLED:
                # Return the persisted fill, never a recalculated replacement.
                return _public(stored)

            if status != PENDING:
                raise OrderConflict(
                    "Order is not eligible for replay"
                )

            stored["status"] = FILLED
            stored["fill"] = fill
            stored["updated_at"] = (
                datetime.now(timezone.utc).isoformat()
            )

            cur.execute(
                """
                UPDATE playgo_private.documents
                SET body = %s::jsonb,
                    revision = revision + 1,
                    updated_at = NOW()
                WHERE collection_name = %s
                  AND document_id = %s
                """,
                (
                    json.dumps(stored),
                    COLLECTION,
                    client_order_id,
                ),
            )

            if cur.rowcount != 1:
                raise RuntimeError(
                    "Demo order status update failed"
                )

            return _public(stored)


def pending_orders(conn, limit=50):
    """Return persisted pending DEMO orders."""
    _validate_limit(limit, 200)

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT body
            FROM playgo_private.documents
            WHERE collection_name = %s
              AND body->>'status' = %s
            ORDER BY updated_at, document_id
            LIMIT %s
            """,
            (COLLECTION, PENDING, limit),
        )

        rows = cur.fetchall()

    return [
        _public(_decode(row[0]))
        for row in rows
    ]


def recover_pending(conn, limit=50):
    """Recover pending DEMO orders using normal idempotent submission.

    Individual validation or order-conflict failures are reported and
    recovery continues.

    Database connection and transaction failures propagate to the
    caller rather than being silently treated as order errors.
    """
    _validate_limit(limit, 200)

    recovered = []
    errors = []

    rows = pending_orders(conn, limit)

    for row in rows:
        client_order_id = row["client_order_id"]

        try:
            result = submit_demo_order(
                conn,
                client_order_id=client_order_id,
                **row["request"],
            )

            if result["status"] != FILLED:
                raise RuntimeError(
                    "Recovered order is not filled"
                )

            recovered.append(client_order_id)

        except (
            DemoOrderError,
            OrderConflict,
            ValueError,
            TypeError,
            KeyError,
        ) as exc:
            errors.append(
                {
                    "client_order_id": client_order_id,
                    "error": type(exc).__name__,
                }
            )

    return {
        "mode": "DEMO",
        "recovered": recovered,
        "errors": errors,
    }


def list_orders(
    conn,
    *,
    limit=25,
    offset=0,
    pair=None,
    side=None,
    status=None,
    date_from=None,
    date_to=None,
):
    """Return paginated DEMO order history with parameterized filters.

    Dates are inclusive UTC calendar dates.
    """

    _validate_limit(limit, 100)

    if type(offset) is not int or not 0 <= offset <= 100000:
        raise ValueError(
            "Offset must be between 0 and 100000"
        )

    if pair is not None and pair not in ALLOWED_PAIRS:
        raise ValueError("Unsupported currency pair")

    if side is not None and side not in ALLOWED_SIDES:
        raise ValueError("Unsupported order direction")

    if status is not None and status not in ALLOWED_STATUSES:
        raise ValueError("Unsupported order status")

    try:
        start = (
            date.fromisoformat(date_from)
            if date_from
            else None
        )
        end = (
            date.fromisoformat(date_to)
            if date_to
            else None
        )
    except (ValueError, TypeError) as exc:
        raise ValueError(
            "Dates must use YYYY-MM-DD"
        ) from exc

    if start and end and start > end:
        raise ValueError(
            "date_from cannot exceed date_to"
        )

    conditions = ["collection_name=%s"]
    params = [COLLECTION]

    if pair:
        conditions.append(
            "body->'request'->>'pair'=%s"
        )
        params.append(pair)

    if side:
        conditions.append(
            "body->'request'->>'side'=%s"
        )
        params.append(side)

    if status:
        conditions.append(
            "body->>'status'=%s"
        )
        params.append(status)

    if start:
        conditions.append(
            "(body->>'created_at')::timestamptz >= %s::date"
        )
        params.append(start.isoformat())

    if end:
        conditions.append(
            "(body->>'created_at')::timestamptz < "
            "(%s::date + interval '1 day')"
        )
        params.append(end.isoformat())

    where = " AND ".join(conditions)

    with conn.cursor() as cur:

        cur.execute(
            "SELECT count(*) "
            "FROM playgo_private.documents "
            "WHERE " + where,
            params,
        )

        total = cur.fetchone()[0]

        cur.execute(
            "SELECT body "
            "FROM playgo_private.documents "
            "WHERE " + where +
            " order by "
            "(body->>'created_at')::timestamptz DESC, "
            "document_id DESC "
            "LIMIT %s OFFSET %s",
            [*params, limit, offset],
        )

        results = [
            _public(_decode(row[0]))
            for row in cur.fetchall()
        ]

    return {
        "mode": "DEMO",
        "total": total,
        "limit": limit,
        "offset": offset,
        "orders": results,
    }


def get_order(conn, client_order_id):
    """Return a persisted DEMO order or None.

    Never expose the private request fingerprint.
    """
    _validate_order_id(client_order_id)

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT body
            FROM playgo_private.documents
            WHERE collection_name = %s
              AND document_id = %s
            """,
            (COLLECTION, client_order_id),
        )

        row = cur.fetchone()

    if row is None:
        return None

    return _public(_decode(row[0]))
