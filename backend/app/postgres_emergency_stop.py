"""Phase 7D: one-way, durable PAPER automation emergency stop.

Emergency stop can only be activated here. No re-arm or automated execution
endpoint is exposed. Uses the authoritative PAPER state row lock and CAS.
"""
from copy import deepcopy
from datetime import datetime, timezone

from app import postgres_ledger
from app import postgres_state


def engage(conn, *, expected_revision, reason):
    if type(expected_revision) is not int or expected_revision < 0:
        raise ValueError("Invalid expected revision")
    if not isinstance(reason, str) or not 3 <= len(reason.strip()) <= 200:
        raise ValueError("Emergency stop reason must be 3-200 characters")
    reason = reason.strip()
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute(
                """select revision from playgo_private.documents
                   where collection_name=%s and document_id=%s for update""",
                (postgres_ledger.COLLECTION, postgres_ledger.STATE_ID))
            if cur.fetchone() is None:
                raise RuntimeError("PAPER state is not initialized")
        previous = postgres_state.load(conn)
        # Retry of an already-engaged stop must be harmless even with a stale
        # revision; never remove or rewrite the original audit record.
        if previous.get("automation_emergency_stop") is True:
            return previous
        if previous["revision"] != expected_revision:
            raise postgres_ledger.StaleStateError(
                "PAPER state changed; reload before engaging emergency stop")
        proposed = deepcopy(previous)
        proposed["automation_emergency_stop"] = True
        proposed["paused"] = True
        proposed.setdefault("logs", []).insert(0, {
            "id": "emergency-stop:" + str(expected_revision + 1),
            "time": datetime.now(timezone.utc).isoformat(),
            "agent": "Supervisor",
            "message": "PAPER automation emergency stop engaged",
            "reason": reason,
        })
        proposed["logs"] = proposed["logs"][:100]
        revision = postgres_state.commit(conn, previous, proposed)
        proposed["revision"] = revision
        return proposed
