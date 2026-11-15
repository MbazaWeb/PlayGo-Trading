"""Phase 7C: durable, concurrency-safe PAPER signal decisions.

Uses the existing private documents primary key for deduplication. No trading
execution, broker access, state mutation or accounting journal writes.
"""
from datetime import datetime, timezone
from hashlib import sha256
import json
import re

import postgres_signal_validator as validator
import postgres_state

COLLECTION = "paper_signal_decisions"


class SignalConflict(ValueError):
    pass


def _decode(body):
    return body if isinstance(body, dict) else json.loads(body)


def _fingerprint(signal):
    return sha256(json.dumps(signal, sort_keys=True, separators=(",", ":"),
                             allow_nan=False).encode("utf-8")).hexdigest()


def record_signal(conn, *, signal):
    """Atomically record one decision; identical retries return the first.

    The first decision is immutable. A reused ID with different content fails.
    A failed transaction leaves no decision behind. Validation is performed
    against the current PAPER state under its row lock.
    """
    if not isinstance(signal, dict):
        raise ValueError("Signal must be an object")
    signal_id = signal.get("signal_id")
    if not isinstance(signal_id, str) or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", signal_id):
        raise ValueError("Invalid signal ID")
    try:
        fingerprint = _fingerprint(signal)
    except (TypeError, ValueError) as exc:
        raise ValueError("Signal must contain JSON-compatible finite values") from exc
    with conn.transaction():
        with conn.cursor() as cur:
            # Serialize this ID across workers using the documents unique key.
            # Placeholder is not externally visible until commit.
            placeholder = {"signal_id": signal_id, "fingerprint": fingerprint,
                           "status": "PENDING"}
            cur.execute(
                """insert into playgo_private.documents
                   (collection_name, document_id, body, revision)
                   values (%s, %s, %s::jsonb, 0)
                   on conflict (collection_name, document_id) do nothing""",
                (COLLECTION, signal_id, json.dumps(placeholder)))
            cur.execute(
                """select body from playgo_private.documents
                   where collection_name=%s and document_id=%s for update""",
                (COLLECTION, signal_id))
            row = cur.fetchone()
            if row is None:
                raise RuntimeError("Signal decision not persisted")
            stored = _decode(row[0])
            if stored.get("fingerprint") != fingerprint:
                raise SignalConflict("Signal ID reused with different payload")
            if stored.get("status") in ("ACCEPTED", "REJECTED"):
                return stored["decision"]
            if stored.get("status") != "PENDING":
                raise SignalConflict("Invalid signal decision status")
            cur.execute(
                """select revision from playgo_private.documents
                   where collection_name=%s and document_id=%s for update""",
                ("app_state", "paper-trading-state"))
            if cur.fetchone() is None:
                raise RuntimeError("PAPER state not initialized")
            state = postgres_state.load(conn)
            decision = validator.validate_signal(signal, state)
            # Screening does not authorize execution; record only.
            decision["recorded_at"] = datetime.now(timezone.utc).isoformat()
            stored["status"] = "ACCEPTED" if decision["accepted"] else "REJECTED"
            stored["decision"] = decision
            cur.execute(
                """update playgo_private.documents
                   set body=%s::jsonb, revision=revision+1, updated_at=now()
                   where collection_name=%s and document_id=%s""",
                (json.dumps(stored), COLLECTION, signal_id))
            return decision


def get_signal(conn, signal_id):
    if not isinstance(signal_id, str) or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", signal_id):
        raise ValueError("Invalid signal ID")
    with conn.cursor() as cur:
        cur.execute(
            """select body from playgo_private.documents
               where collection_name=%s and document_id=%s""",
            (COLLECTION, signal_id))
        row = cur.fetchone()
    if row is None:
        return None
    stored = _decode(row[0])
    return stored.get("decision")
