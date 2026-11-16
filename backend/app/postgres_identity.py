"""PostgreSQL-backed, single-owner PlayGo authentication.

This module is deliberately separate from the legacy MongoDB routes until the
complete FastAPI persistence cutover has been tested. Never import into a
browser bundle or expose the database connection string.
"""
from datetime import datetime, timedelta, timezone
from hashlib import pbkdf2_hmac, sha256
import hmac
import os
import re
import secrets

COMPANY_ID = "PLAYGO_TANZANIA_LIMITED"
ITERATIONS = 600_000
USERNAME = re.compile(r"^[a-z][a-z0-9_]{2,31}$")


class OwnerAuthError(ValueError):
    pass


def _digest(password: str, salt: bytes) -> str:
    return pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERATIONS).hex()


def bootstrap_owner(conn, *, username: str, password: str) -> dict:
    """Requires caller to validate the out-of-band bootstrap secret first.

    A unique company_id constraint prevents concurrent duplicate owner creation.
    """
    if not isinstance(username, str) or not USERNAME.fullmatch(username):
        raise OwnerAuthError("Invalid username")
    if not isinstance(password, str) or not 12 <= len(password) <= 256:
        raise OwnerAuthError("Password must be 12-256 characters")
    salt = os.urandom(16)
    owner_id = secrets.token_hex(16)
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute(
                """insert into playgo_private.owners
                   (owner_id, company_id, username, salt, password_hash)
                   values (%s, %s, %s, %s, %s)
                   on conflict do nothing returning owner_id""",
                (owner_id, COMPANY_ID, username, salt.hex(), _digest(password, salt)),
            )
            row = cur.fetchone()
            if row is None:
                raise OwnerAuthError("Company owner already exists")
    return {"user_id": owner_id, "username": username}


def login(conn, *, username: str, password: str) -> dict:
    with conn.cursor() as cur:
        cur.execute(
            """select owner_id, salt, password_hash, disabled
               from playgo_private.owners
               where company_id = %s and username = %s""",
            (COMPANY_ID, username if isinstance(username, str) else ""),
        )
        row = cur.fetchone()
    salt = bytes.fromhex(row[1]) if row else bytes(16)
    candidate = _digest(password if isinstance(password, str) else "", salt)
    if not row or row[3] or not hmac.compare_digest(candidate, row[2]):
        raise OwnerAuthError("Invalid credentials")
    token = secrets.token_urlsafe(48)
    expiry = datetime.now(timezone.utc) + timedelta(hours=8)
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute(
                """insert into playgo_private.owner_sessions
                   (token_digest, owner_id, expires_at)
                   values (%s, %s, %s)""",
                (sha256(token.encode()).hexdigest(), row[0], expiry),
            )
    return {"access_token": token, "token_type": "bearer", "expires_at": expiry.isoformat()}


def verify_session(conn, authorization: str) -> str:
    if not isinstance(authorization, str) or not authorization.startswith("Bearer "):
        raise OwnerAuthError("Bearer session required")
    token = authorization[7:]
    if len(token) != 64:
        raise OwnerAuthError("Invalid session")
    with conn.cursor() as cur:
        cur.execute(
            """select o.owner_id from playgo_private.owner_sessions s
               join playgo_private.owners o on o.owner_id = s.owner_id
               where s.token_digest = %s and s.expires_at > now()
                 and o.company_id = %s and o.disabled = false""",
            (sha256(token.encode()).hexdigest(), COMPANY_ID),
        )
        row = cur.fetchone()
    if row is None:
        raise OwnerAuthError("Invalid or expired session")
    return row[0]


def revoke_session(conn, authorization: str) -> None:
    owner_id = verify_session(conn, authorization)
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute(
                """delete from playgo_private.owner_sessions
                   where token_digest = %s and owner_id = %s""",
                (sha256(authorization[7:].encode()).hexdigest(), owner_id),
            )
