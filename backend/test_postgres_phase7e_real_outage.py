"""Manual Phase 7E.3 real outage test against an isolated local PostgreSQL.

Run only with explicit opt-in. Never stops/starts Docker or changes database
records. Operator stops and restarts the isolated container in another shell.
Authentication is replaced ONLY in this in-process test client.
"""
import os
from unittest.mock import patch

import psycopg
from psycopg.conninfo import conninfo_to_dict
from fastapi.testclient import TestClient

import postgres_api
import postgres_operational_monitor


def require_isolated_dsn():
    if os.getenv("PLAYGO_RUN_ISOLATED_OUTAGE_TEST") != "1":
        raise SystemExit("Set PLAYGO_RUN_ISOLATED_OUTAGE_TEST=1 to opt in")
    dsn = os.getenv("PLAYGO_ISOLATED_DATABASE_URL", "")
    try:
        params = conninfo_to_dict(dsn)
    except psycopg.Error as exc:
        raise SystemExit("Invalid isolated DSN") from exc
    if (params.get("dbname") != "playgo_phase7d_isolated"
            or params.get("host") not in ("127.0.0.1", "localhost", "::1")
            or params.get("hostaddr")
            or os.getenv("DATABASE_URL") == dsn):
        raise SystemExit("Refusing non-isolated PostgreSQL DSN")
    return dsn


def probe(client):
    response = client.get("/api/paper/automation/operational-status",
                          headers={"Authorization": "Bearer isolated-test"})
    return response.status_code, response.json()


def main():
    dsn = require_isolated_dsn()
    with psycopg.connect(dsn, connect_timeout=3) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass('playgo_private.documents')")
            if cur.fetchone()[0] is None:
                raise SystemExit("Isolated database not initialized")
    # Keep the same Python process alive across outage and recovery to test
    # consecutive failure counts. No real credentials are sent over HTTP.
    with patch.object(postgres_api, "connect",
                      side_effect=lambda: psycopg.connect(dsn, connect_timeout=2)), \
         patch.object(postgres_api, "owner", return_value="isolated-test"):
        client = TestClient(postgres_api.app)
        code, body = probe(client)
        if code != 200 or body.get("eligible") is not False:
            raise AssertionError(f"Initial healthy probe failed: HTTP {code}")
        print("PASS: initial isolated PostgreSQL status healthy; execution disabled")
        input("STOP ONLY the playgo-phase7d-db Docker container, then press Enter...")
        for expected in (1, 2):
            code, body = probe(client)
            detail = body.get("detail", {})
            if (code != 503 or detail.get("eligible") is not False
                    or detail.get("execution") != "DISABLED"
                    or detail.get("monitor", {}).get("consecutive_failures") != expected):
                raise AssertionError(f"Outage probe {expected} failed: HTTP {code}")
            print(f"PASS: real outage HTTP 503, consecutive failures {expected}")
        input("START ONLY the playgo-phase7d-db Docker container, wait until ready, then press Enter...")
        code, body = probe(client)
        if (code != 200 or body.get("eligible") is not False
                or body.get("monitor", {}).get("consecutive_failures") != 0
                or body.get("monitor", {}).get("last_recovery_at") is None):
            raise AssertionError(f"Recovery probe failed: HTTP {code}")
        print("PASS: real PostgreSQL recovery; failure streak cleared; execution disabled")
        print("Phase 7E.3: ALL CHECKS PASSED")


if __name__ == "__main__":
    main()
