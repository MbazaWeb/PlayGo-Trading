"""Isolated development identities and tenant-scoped paper accounts.

Opaque random bearer sessions are stored only as SHA-256 digests. Passwords
use PBKDF2-HMAC-SHA256. Not a production identity provider.
"""
from datetime import datetime, timedelta, timezone
from hashlib import pbkdf2_hmac, sha256
import hmac
import os
import re
import secrets
from typing import Any
from pymongo.collection import Collection
from pymongo.errors import DuplicateKeyError

ITERATIONS = 600_000
USERNAME = re.compile(r"^[a-z][a-z0-9_]{2,31}$")


class IdentityError(ValueError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _digest(password: str, salt: bytes) -> str:
    return pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERATIONS).hex()


def register(users: Collection, *, username: str, password: str) -> dict[str, str]:
    if not isinstance(username, str) or not USERNAME.fullmatch(username):
        raise IdentityError("Username must be 3–32 lowercase letters, digits or underscores")
    if not isinstance(password, str) or not 12 <= len(password) <= 256:
        raise IdentityError("Password must be 12–256 characters")
    from company import COMPANY_ID
    if users.find_one({"company_id": COMPANY_ID}):
        raise IdentityError("Company owner already exists; additional users disabled")
    salt = os.urandom(16)
    user_id = secrets.token_hex(16)
    try:
        users.insert_one({"_id": user_id, "username": username,
                          "salt": salt.hex(), "password_hash": _digest(password, salt),
                          "created_at": _now().isoformat(), "disabled": False,
                          "company_id": COMPANY_ID, "role": "OWNER"})
    except DuplicateKeyError as exc:
        raise IdentityError("Username unavailable") from exc
    return {"user_id": user_id, "username": username}


def login(users: Collection, sessions: Collection, *, username: str,
          password: str) -> dict[str, Any]:
    from company import COMPANY_ID
    user = users.find_one({"username": username, "company_id": COMPANY_ID, "role": "OWNER"}) if isinstance(username, str) else None
    # Perform password hashing even for unknown users to reduce timing signals.
    salt = bytes.fromhex(user["salt"]) if user else bytes(16)
    digest = _digest(password if isinstance(password, str) else "", salt)
    if not user or user.get("disabled") or not hmac.compare_digest(digest, user["password_hash"]):
        raise IdentityError("Invalid credentials")
    token = secrets.token_urlsafe(48)
    expiry = _now() + timedelta(hours=8)
    sessions.insert_one({"_id": sha256(token.encode()).hexdigest(),
                         "user_id": user["_id"], "expires_at": expiry,
                         "created_at": _now()})
    return {"access_token": token, "token_type": "bearer", "expires_at": expiry.isoformat()}


def verify_session(sessions: Collection, authorization: str) -> str:
    if not authorization.startswith("Bearer "):
        raise IdentityError("Bearer session required")
    token = authorization[7:]
    if len(token) != 64:
        raise IdentityError("Invalid session")
    row = sessions.find_one({"_id": sha256(token.encode()).hexdigest(),
                             "expires_at": {"$gt": _now()}})
    if not row:
        raise IdentityError("Invalid or expired session")
    return row["user_id"]


def revoke_session(sessions: Collection, authorization: str) -> None:
    user_id = verify_session(sessions, authorization)
    sessions.delete_one({"_id": sha256(authorization[7:].encode()).hexdigest(),
                         "user_id": user_id})


def ensure_paper_account(accounts: Collection, user_id: str) -> dict[str, Any]:
    """Atomic first-time account initialization; no legacy data copied."""
    if not isinstance(user_id, str) or not re.fullmatch(r"[0-9a-f]{32}", user_id):
        raise IdentityError("Invalid user ID")
    key = "USER:" + user_id
    accounts.update_one({"_id": key},
                        {"$setOnInsert": {"user_id": user_id, "mode": "PAPER",
                                          "currency": "USD", "balance_cents": 0,
                                          "revision": 0, "created_at": _now().isoformat()}},
                        upsert=True)
    row = accounts.find_one({"_id": key, "user_id": user_id})
    if not row:
        raise IdentityError("Account unavailable")
    return {"user_id": user_id, "mode": row["mode"], "currency": row["currency"],
            "balance_cents": row["balance_cents"], "revision": row["revision"]}


def account_for_session(accounts: Collection, sessions: Collection,
                        authorization: str) -> dict[str, Any]:
    return ensure_paper_account(accounts, verify_session(sessions, authorization))
