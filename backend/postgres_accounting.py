"""Atomic, paper-only PostgreSQL accounting. Not yet wired to FastAPI.

Each journal is a double-entry posting in integer USD cents. A row lock
serializes writers; the unique transaction ID and reversal index enforce
idempotency. No live-money payment rails exist here.
"""
import json
from datetime import datetime

from accounting import (
    ACCOUNT_ID, ACCOUNTS, NORMAL, InsufficientFunds, LedgerConflict,
    apply_lines, journal_lines, opening_account,
)

COLLECTION = "paper_accounting_accounts"


def _decode(value):
    return value if isinstance(value, dict) else json.loads(value)


def _journal(row):
    return {
        "transaction_id": row[0], "kind": row[1], "amount_cents": row[2],
        "reference": row[3], "lines": row[4] if isinstance(row[4], list) else json.loads(row[4]),
        "created_at": row[5].isoformat() if isinstance(row[5], datetime) else str(row[5]),
        "currency": "USD", "mode": "PAPER",
    }


def initialize(conn):
    """Idempotent creation of zero-funded paper accounting books."""
    opening = opening_account()
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute(
                """insert into playgo_private.documents
                   (collection_name, document_id, body, revision)
                   values (%s, %s, %s::jsonb, 0)
                   on conflict do nothing""",
                (COLLECTION, ACCOUNT_ID, json.dumps(opening)),
            )


def post(conn, *, transaction_id: str, kind: str, amount_cents: int,
         reference: str = "") -> dict:
    if not isinstance(transaction_id, str) or not 1 <= len(transaction_id) <= 128:
        raise ValueError("Invalid transaction ID")
    if not isinstance(reference, str) or len(reference) > 256:
        raise ValueError("Invalid reference")
    if kind in ("REALIZED_GAIN", "REALIZED_LOSS") and not (
        transaction_id.startswith("TRADE:") and reference == "CLOSED:" + transaction_id[6:]
    ):
        raise ValueError("Realized P&L requires matching closed-trade reference")
    if kind != "REVERSAL":
        lines = journal_lines(kind, amount_cents)
    else:
        lines = None
    with conn.transaction():
        with conn.cursor() as cur:
            # Serialize all journal writers, including duplicate requests.
            cur.execute(
                """select body, revision from playgo_private.documents
                   where collection_name=%s and document_id=%s for update""",
                (COLLECTION, ACCOUNT_ID),
            )
            account_row = cur.fetchone()
            if account_row is None:
                raise RuntimeError("Accounting account not initialized")
            cur.execute(
                """select transaction_id, kind, amount_cents, reference, lines, created_at
                   from playgo_private.accounting_journals where transaction_id=%s""",
                (transaction_id,),
            )
            existing = cur.fetchone()
            if existing:
                if (existing[1], existing[2], existing[3]) != (kind, amount_cents, reference):
                    raise LedgerConflict("Transaction ID reused with different values")
                return _journal(existing)
            if kind == "REVERSAL":
                cur.execute(
                    """select kind, amount_cents, lines
                       from playgo_private.accounting_journals
                       where transaction_id=%s""",
                    (reference,),
                )
                original = cur.fetchone()
                if not original or original[0] == "REVERSAL":
                    raise ValueError("Reversal requires an existing non-reversal journal")
                if type(amount_cents) is not int or amount_cents != original[1]:
                    raise ValueError("Reversal amount must match original journal")
                original_lines = original[2] if isinstance(original[2], list) else json.loads(original[2])
                lines = [
                    {"account": x["account"], "debit_cents": x["credit_cents"],
                     "credit_cents": x["debit_cents"]}
                    for x in original_lines
                ]
                cur.execute(
                    """select 1 from playgo_private.accounting_journals
                       where kind='REVERSAL' and reference=%s""",
                    (reference,),
                )
                if cur.fetchone():
                    raise LedgerConflict("Original transaction already reversed")
            account = _decode(account_row[0])
            updated = apply_lines(account["balances"], lines)
            account["balances"] = updated
            account["revision"] = int(account_row[1]) + 1
            cur.execute(
                """update playgo_private.documents
                   set body=%s::jsonb, revision=%s, updated_at=now()
                   where collection_name=%s and document_id=%s""",
                (json.dumps(account), account["revision"], COLLECTION, ACCOUNT_ID),
            )
            cur.execute(
                """insert into playgo_private.accounting_journals
                   (transaction_id, kind, amount_cents, reference, lines)
                   values (%s, %s, %s, %s, %s::jsonb)
                   returning transaction_id, kind, amount_cents, reference, lines, created_at""",
                (transaction_id, kind, amount_cents, reference, json.dumps(lines)),
            )
            return _journal(cur.fetchone())


def recent_journals(conn, limit: int = 50) -> list[dict]:
    if type(limit) is not int or not 1 <= limit <= 200:
        raise ValueError("Invalid journal limit")
    with conn.cursor() as cur:
        cur.execute(
            """select transaction_id, kind, amount_cents, reference, lines, created_at
               from playgo_private.accounting_journals
               order by created_at desc, transaction_id desc limit %s""",
            (limit,),
        )
        return [_journal(row) for row in cur.fetchall()]


def reconcile(conn) -> dict:
    with conn.cursor() as cur:
        cur.execute(
            """select body, revision from playgo_private.documents
               where collection_name=%s and document_id=%s""",
            (COLLECTION, ACCOUNT_ID),
        )
        row = cur.fetchone()
        if row is None:
            raise RuntimeError("Accounting account not initialized")
        account = _decode(row[0])
        revision = int(row[1])
        cur.execute(
            """select transaction_id, lines from playgo_private.accounting_journals
               order by created_at, transaction_id"""
        )
        rows = cur.fetchall()
    replay = {name: 0 for name in ACCOUNTS}
    issues = []
    for txid, value in rows:
        try:
            lines = value if isinstance(value, list) else json.loads(value)
            if sum(x["debit_cents"] for x in lines) != sum(x["credit_cents"] for x in lines):
                raise ValueError("Unbalanced journal")
            for line in lines:
                replay[line["account"]] += NORMAL[line["account"]] * (
                    line["debit_cents"] - line["credit_cents"]
                )
        except (KeyError, TypeError, ValueError):
            issues.append("INVALID_JOURNAL:" + txid)
    stored = account["balances"]
    differences = {name: stored.get(name, 0) - replay[name] for name in ACCOUNTS}
    if any(differences.values()):
        issues.append("BALANCE_MISMATCH")
    if sum(replay[name] * NORMAL[name] for name in ACCOUNTS) != 0:
        issues.append("TRIAL_BALANCE_MISMATCH")
    if stored.get("CASH", -1) < 0:
        issues.append("NEGATIVE_CASH")
    if revision != len(rows):
        issues.append("REVISION_JOURNAL_COUNT_MISMATCH")
    return {
        "mode": "PAPER", "currency": "USD", "consistent": not issues,
        "journal_count": len(rows), "revision": revision,
        "balances_cents": stored, "replayed_balances_cents": replay,
        "differences_cents": differences, "issues": issues,
    }
