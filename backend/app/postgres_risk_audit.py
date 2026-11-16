"""Phase 7D: durable, idempotent PAPER risk assessments.

Explicit audit requests only. Preview remains read-only. The authoritative
PAPER state is never changed, and no trading execution is possible.
"""
from datetime import datetime, timezone
from hashlib import sha256
import json
import re

from app import postgres_accounting
from app import postgres_automated_risk
from app import postgres_state

COLLECTION = "paper_risk_assessments"
ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}")


class AuditConflict(ValueError):
    pass


def _decode(value):
    return value if isinstance(value, dict) else json.loads(value)


def record(conn, *, assessment_id, proposal):
    if not isinstance(assessment_id, str) or not ID_PATTERN.fullmatch(assessment_id):
        raise ValueError("Invalid assessment ID")
    if not isinstance(proposal, dict):
        raise ValueError("Invalid proposal")
    try:
        fingerprint = sha256(json.dumps(
            proposal, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")).hexdigest()
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid JSON proposal") from exc
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute(
                """insert into playgo_private.documents
                   (collection_name, document_id, body, revision)
                   values (%s, %s, %s::jsonb, 0)
                   on conflict (collection_name, document_id) do nothing""",
                (COLLECTION, assessment_id, json.dumps({
                    "assessment_id": assessment_id, "fingerprint": fingerprint,
                    "status": "PENDING"})))
            cur.execute(
                """select body from playgo_private.documents
                   where collection_name=%s and document_id=%s for update""",
                (COLLECTION, assessment_id))
            row = cur.fetchone()
            if row is None:
                raise RuntimeError("Risk audit record unavailable")
            existing = _decode(row[0])
            if existing.get("fingerprint") != fingerprint:
                raise AuditConflict("Assessment ID reused with different proposal")
            if existing.get("status") == "RECORDED":
                return existing["result"]
            if existing.get("status") != "PENDING":
                raise AuditConflict("Invalid risk audit status")
            # Serialize against PAPER state writes to get an authoritative
            # state revision for this durable assessment.
            cur.execute(
                """select revision from playgo_private.documents
                   where collection_name='app_state'
                     and document_id='paper-trading-state' for update""")
            if cur.fetchone() is None:
                raise RuntimeError("PAPER state not initialized")
            state = postgres_state.load(conn)
            accounting = postgres_accounting.reconcile(conn)
            decision = postgres_automated_risk.assess(
                state, accounting, proposal=proposal, automation_enabled=False)
            result = {
                "mode": "PAPER", "execution": "OBSERVATION_ONLY",
                "assessment_id": assessment_id,
                "state_revision": state["revision"],
                "recorded_at": datetime.now(timezone.utc).isoformat(),
                "decision": decision,
            }
            existing["status"] = "RECORDED"
            existing["result"] = result
            cur.execute(
                """update playgo_private.documents
                   set body=%s::jsonb, revision=revision+1, updated_at=now()
                   where collection_name=%s and document_id=%s""",
                (json.dumps(existing), COLLECTION, assessment_id))
            return result


def get(conn, assessment_id):
    if not isinstance(assessment_id, str) or not ID_PATTERN.fullmatch(assessment_id):
        raise ValueError("Invalid assessment ID")
    with conn.cursor() as cur:
        cur.execute(
            """select body from playgo_private.documents
               where collection_name=%s and document_id=%s""",
            (COLLECTION, assessment_id))
        row = cur.fetchone()
    if row is None:
        return None
    stored = _decode(row[0])
    return stored.get("result") if stored.get("status") == "RECORDED" else None


def list_recent(conn, *, limit=25, offset=0):
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("Invalid limit")
    if type(offset) is not int or not 0 <= offset <= 100000:
        raise ValueError("Invalid offset")
    with conn.cursor() as cur:
        cur.execute(
            """select count(*) from playgo_private.documents
               where collection_name=%s and body->>'status'='RECORDED'""",
            (COLLECTION,))
        total = cur.fetchone()[0]
        cur.execute(
            """select body from playgo_private.documents
               where collection_name=%s and body->>'status'='RECORDED'
               order by updated_at desc, document_id desc limit %s offset %s""",
            (COLLECTION, limit, offset))
        results = [_decode(row[0])["result"] for row in cur.fetchall()]
    return {"mode": "PAPER", "execution": "OBSERVATION_ONLY",
            "total": total, "limit": limit, "offset": offset,
            "assessments": results}
