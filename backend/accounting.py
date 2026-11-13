"""Independent USD paper-money double-entry ledger.

All monetary values are signed integer cents; no float arithmetic.
Every journal is immutable by application convention and balances to zero.
This is separate from the legacy trading state and cannot move real money.
"""
from datetime import datetime, timezone
from typing import Any
from pymongo.collection import Collection
from pymongo.errors import DuplicateKeyError

ACCOUNT_ID = "paper-usd-ledger-v1"
ACCOUNTS = ("CASH", "CONTRIBUTED_CAPITAL", "REALIZED_PNL", "FEES", "WITHDRAWALS")
KINDS = ("CAPITAL_IN", "WITHDRAWAL", "REALIZED_GAIN", "REALIZED_LOSS", "FEE")
NORMAL = {"CASH": 1, "CONTRIBUTED_CAPITAL": -1, "REALIZED_PNL": -1,
          "FEES": 1, "WITHDRAWALS": 1}


class LedgerConflict(ValueError):
    pass


class InsufficientFunds(ValueError):
    pass


def opening_account() -> dict[str, Any]:
    return {"_id": ACCOUNT_ID, "mode": "PAPER", "currency": "USD",
            "revision": 0, "balances": {account: 0 for account in ACCOUNTS}}


def journal_lines(kind: str, amount_cents: int) -> list[dict[str, Any]]:
    if kind not in KINDS:
        raise ValueError("Unsupported journal kind")
    if type(amount_cents) is not int or amount_cents <= 0 or amount_cents > 10**12:
        raise ValueError("Amount must be positive integer cents within permitted bounds")
    mapping = {
        "CAPITAL_IN": ("CASH", "CONTRIBUTED_CAPITAL"),
        "WITHDRAWAL": ("WITHDRAWALS", "CASH"),
        "REALIZED_GAIN": ("CASH", "REALIZED_PNL"),
        "REALIZED_LOSS": ("REALIZED_PNL", "CASH"),
        "FEE": ("FEES", "CASH"),
    }
    debit, credit = mapping[kind]
    return [{"account": debit, "debit_cents": amount_cents, "credit_cents": 0},
            {"account": credit, "debit_cents": 0, "credit_cents": amount_cents}]


def apply_lines(balances: dict[str, int], lines: list[dict[str, Any]]) -> dict[str, int]:
    if sum(x["debit_cents"] for x in lines) != sum(x["credit_cents"] for x in lines):
        raise ValueError("Unbalanced journal")
    updated = dict(balances)
    for line in lines:
        name = line["account"]
        if name not in NORMAL:
            raise ValueError("Unknown ledger account")
        updated[name] += NORMAL[name] * (line["debit_cents"] - line["credit_cents"])
    if updated["CASH"] < 0:
        raise InsufficientFunds("Insufficient virtual cash")
    return updated


def post(collection: Collection, journals: Collection, *, transaction_id: str,
         kind: str, amount_cents: int, reference: str = "") -> dict[str, Any]:
    """Atomic CAS balance update + unique immutable journal insert.

    Duplicate transaction IDs are safe to retry only with identical payload.
    On CAS conflict the caller must retry with a fresh request.
    """
    if not isinstance(transaction_id, str) or not 1 <= len(transaction_id) <= 128:
        raise ValueError("Invalid transaction ID")
    if not isinstance(reference, str) or len(reference) > 256:
        raise ValueError("Invalid reference")
    lines = journal_lines(kind, amount_cents)
    existing = journals.find_one({"_id": transaction_id})
    if existing:
        if (existing["kind"], existing["amount_cents"], existing["reference"]) != (kind, amount_cents, reference):
            raise LedgerConflict("Transaction ID already used for different values")
        return public_journal(existing)
    account = collection.find_one({"_id": ACCOUNT_ID})
    if account is None:
        raise RuntimeError("Ledger account not initialized")
    updated = apply_lines(account["balances"], lines)
    record = {"_id": transaction_id, "account_id": ACCOUNT_ID, "mode": "PAPER",
              "currency": "USD", "kind": kind, "amount_cents": amount_cents,
              "reference": reference, "lines": lines,
              "created_at": datetime.now(timezone.utc).isoformat()}
    try:
        with collection.database.client.start_session() as session:
            with session.start_transaction():
                result = collection.update_one(
                    {"_id": ACCOUNT_ID, "revision": account["revision"]},
                    {"$set": {"balances": updated}, "$inc": {"revision": 1}},
                    session=session,
                )
                if result.matched_count != 1:
                    raise LedgerConflict("Account revision changed; retry transaction")
                journals.insert_one(record, session=session)
    except DuplicateKeyError:
        existing = journals.find_one({"_id": transaction_id})
        if existing and (existing["kind"], existing["amount_cents"], existing["reference"]) == (kind, amount_cents, reference):
            return public_journal(existing)
        raise LedgerConflict("Transaction ID already used for different values")
    return public_journal(record)


def public_journal(row: dict[str, Any]) -> dict[str, Any]:
    return {"transaction_id": row["_id"], "kind": row["kind"],
            "amount_cents": row["amount_cents"], "reference": row["reference"],
            "lines": row["lines"], "created_at": row["created_at"],
            "currency": "USD", "mode": "PAPER"}


def reconcile(collection: Collection, journals: Collection) -> dict[str, Any]:
    """Full journal replay, independently compared to stored account balances."""
    account = collection.find_one({"_id": ACCOUNT_ID})
    if account is None:
        raise RuntimeError("Ledger account not initialized")
    replay = {name: 0 for name in ACCOUNTS}
    problems: list[str] = []
    count = 0
    for row in journals.find({"account_id": ACCOUNT_ID}).sort("_id", 1):
        count += 1
        try:
            lines = row["lines"]
            # Replay signed balances without enforcing cash positivity at each
            # alphabetical ID; journals are not necessarily sorted by time.
            if sum(x["debit_cents"] for x in lines) != sum(x["credit_cents"] for x in lines):
                raise ValueError("Unbalanced journal")
            for line in lines:
                name = line["account"]
                replay[name] += NORMAL[name] * (line["debit_cents"] - line["credit_cents"])
        except (KeyError, TypeError, ValueError):
            problems.append("INVALID_JOURNAL:" + str(row.get("_id")))
    stored = account["balances"]
    differences = {name: stored.get(name, 0) - replay[name] for name in ACCOUNTS}
    if any(differences.values()):
        problems.append("BALANCE_MISMATCH")
    if sum(replay[name] * NORMAL[name] for name in ACCOUNTS) != 0:
        problems.append("TRIAL_BALANCE_MISMATCH")
    if stored.get("CASH", -1) < 0:
        problems.append("NEGATIVE_CASH")
    if account.get("revision") != count:
        problems.append("REVISION_JOURNAL_COUNT_MISMATCH")
    return {"mode": "PAPER", "currency": "USD", "consistent": not problems,
            "journal_count": count, "revision": account["revision"],
            "balances_cents": stored, "replayed_balances_cents": replay,
            "differences_cents": differences, "issues": problems}
