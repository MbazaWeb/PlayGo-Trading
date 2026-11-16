"""Phase 7I.2 opt-in real PostgreSQL owner authentication integration.

STRICTLY disposable Docker database; transaction is always rolled back.
Never prints passwords, tokens or DSNs. No production or broker access.
"""
import os
import secrets
import sys
from hashlib import sha256

import psycopg
from app import postgres_identity as identity
from tests.test_postgres_phase7e_automated_outage import validate, check_identity


class RollbackProbe(Exception):
    pass


def main():
    if os.getenv("PLAYGO_RUN_ISOLATED_AUTH_TEST") != "1":
        raise SystemExit("Opt in with PLAYGO_RUN_ISOLATED_AUTH_TEST=1")
    dsn, container_id = validate()  # Reuse strict disposable Docker identity/DSN checks.
    check_identity(container_id)
    with psycopg.connect(dsn, connect_timeout=5, autocommit=True) as conn:
        with conn.cursor() as cur:
            for table in ("playgo_private.owners", "playgo_private.owner_sessions"):
                cur.execute("SELECT to_regclass(%s)", (table,))
                if cur.fetchone()[0] is None:
                    raise RuntimeError("Isolated authentication schema missing")
            cur.execute("SELECT count(*) FROM playgo_private.owners")
            if cur.fetchone()[0]:
                raise RuntimeError("Isolated database already has owner records; refusing mutation")
        username = "probe_" + secrets.token_hex(6)
        password = secrets.token_urlsafe(32)
        try:
            with conn.transaction():
                identity.bootstrap_owner(conn, username=username, password=password)
                print("PASS: isolated owner bootstrap", flush=True)
                try:
                    identity.login(conn, username=username, password="incorrect")
                except identity.OwnerAuthError:
                    print("PASS: invalid password rejected", flush=True)
                else:
                    raise AssertionError("Incorrect password accepted")
                session = identity.login(conn, username=username, password=password)
                token = session["access_token"]
                header = "Bearer " + token
                owner_id = identity.verify_session(conn, header)
                if not owner_id:
                    raise AssertionError("Session owner missing")
                print("PASS: real PostgreSQL login and session verification", flush=True)
                with conn.cursor() as cur:
                    cur.execute("UPDATE playgo_private.owner_sessions "
                                "SET expires_at = now() - interval '1 second' "
                                "WHERE token_digest = %s",
                                (sha256(token.encode()).hexdigest(),))
                try:
                    identity.verify_session(conn, header)
                except identity.OwnerAuthError:
                    print("PASS: expired session rejected", flush=True)
                else:
                    raise AssertionError("Expired session accepted")
                second = identity.login(conn, username=username, password=password)
                second_header = "Bearer " + second["access_token"]
                identity.revoke_session(conn, second_header)
                try:
                    identity.verify_session(conn, second_header)
                except identity.OwnerAuthError:
                    print("PASS: logout revokes session", flush=True)
                else:
                    raise AssertionError("Revoked session accepted")
                raise RollbackProbe()
        except RollbackProbe:
            pass
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM playgo_private.owners WHERE username = %s",
                        (username,))
            if cur.fetchone()[0] != 0:
                raise AssertionError("Owner probe persisted after rollback")
        print("PASS: isolated owner and sessions rolled back", flush=True)
        print("Phase 7I.2: ALL CHECKS PASSED", flush=True)


if __name__ == "__main__":
    try:
        main()
    except (psycopg.Error, RuntimeError, AssertionError) as exc:
        print("FAIL: isolated PostgreSQL authentication test (" +
              type(exc).__name__ + ")", file=sys.stderr)
        sys.exit(1)
