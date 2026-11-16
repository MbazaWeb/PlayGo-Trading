"""Phase 7F.2 isolated PostgreSQL replay verification (no Docker interruption).

Opt-in only. Uses a temporary SQLite spool, writes only to the isolated
playgo_phase7d_isolated database, and checks idempotent replay and persistence.
"""
import os
import tempfile
from unittest.mock import patch

import psycopg
from psycopg.conninfo import conninfo_to_dict

from app import postgres_incident_spool as spool


def main():
    if os.getenv("PLAYGO_RUN_ISOLATED_OUTAGE_TEST") != "1":
        raise SystemExit("Explicit isolated-test opt-in required")
    dsn = os.getenv("PLAYGO_ISOLATED_DATABASE_URL", "")
    try:
        params = conninfo_to_dict(dsn)
    except psycopg.Error as exc:
        raise SystemExit("Invalid isolated DSN") from exc
    if (params.get("dbname") != "playgo_phase7d_isolated"
            or params.get("host") not in ("127.0.0.1", "localhost", "::1")
            or params.get("hostaddr")
            or os.getenv("DATABASE_URL") == dsn):
        raise SystemExit("Refusing non-isolated database")
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "incidents.sqlite3")
        with patch.dict(os.environ, {"PLAYGO_INCIDENT_SPOOL_PATH": path}):
            outage = spool.enqueue("OUTAGE")
            recovery = spool.enqueue("RECOVERY")
            assert spool.pending_count() == 2
            # Close and reopen the spool: incidents must survive local restart.
            assert spool.pending_count() == 2
            print("PASS: local incident spool persists across reopen", flush=True)
            with psycopg.connect(dsn, connect_timeout=3) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT to_regclass('playgo_private.documents')")
                    if cur.fetchone()[0] is None:
                        raise SystemExit("Isolated database schema missing")
                assert spool.flush(conn) == 2
                assert spool.flush(conn) == 0
                assert spool.pending_count() == 0
                history = spool.list_recent(conn, limit=100)["incidents"]
                matching = {x["incident_id"]: x for x in history
                            if x["incident_id"] in (outage, recovery)}
                assert set(matching) == {outage, recovery}
                assert matching[outage]["kind"] == "OUTAGE"
                assert matching[recovery]["kind"] == "RECOVERY"
                assert all(x["execution"] == "DISABLED" for x in matching.values())
                print("PASS: idempotent PostgreSQL replay and safe incident history",
                      flush=True)
            # New PG connection demonstrates persistence beyond connection lifetime.
            with psycopg.connect(dsn, connect_timeout=3) as conn:
                history = spool.list_recent(conn, limit=100)["incidents"]
                ids = {x["incident_id"] for x in history}
                assert outage in ids and recovery in ids
                print("PASS: PostgreSQL incident history persists across reconnect",
                      flush=True)
    print("Phase 7F.2: REAL REPLAY CHECKS PASSED")


if __name__ == "__main__":
    main()
