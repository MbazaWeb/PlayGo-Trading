"""Phase 7G.3: opt-in isolated PostgreSQL readiness outage/recovery.

Destructive action is limited to the previously validated disposable Docker
container. This test never changes application trading state or live accounts.
"""
import os
import sys
import time

STAGE = 'initial validation'
from unittest.mock import patch

import psycopg
from fastapi.testclient import TestClient

import postgres_api
from test_postgres_phase7e_automated_outage import (
    validate, check_identity, docker, db_ready, wait_until,
)


def check_response(client, expected):
    response = client.get("/api/ready")
    if response.status_code != expected:
        raise AssertionError("Unexpected readiness HTTP status")
    body = response.json()
    if expected == 503:
        body = body.get("detail", {})
        if body.get("ready") is not False or body.get("database") != "UNAVAILABLE":
            raise AssertionError("Readiness failure was not fail-closed")
    else:
        if body.get("ready") is not True or body.get("database") != "CONNECTED":
            raise AssertionError("Readiness did not recover")
    if (body.get("mode") != "PAPER"
            or body.get("execution") != "DISABLED"
            or body.get("automation_enabled") is not False
            or body.get("eligible") is not False):
        raise AssertionError("Readiness violated PAPER-only execution guard")
    return response


def main():
    global STAGE
    STAGE = 'isolated container and DSN validation'
    dsn, container_id = validate()
    STAGE = 'initial database connection'
    wait_until(lambda: db_ready(dsn), 30, "Initial isolated database readiness")
    with patch.object(postgres_api, "connect",
                      side_effect=lambda: psycopg.connect(dsn, connect_timeout=2)):
        client = TestClient(postgres_api.app)
        STAGE = "initial HTTP readiness"
        initial = client.get("/api/ready")
        if initial.status_code != 200:
            with psycopg.connect(dsn, connect_timeout=2) as diagnostic_conn:
                with diagnostic_conn.cursor() as cur:
                    for table in ("playgo_private.owners", "playgo_private.documents"):
                        cur.execute("SELECT to_regclass(%s)", (table,))
                        print("CHECK: " + table + "=" +
                              ("PRESENT" if cur.fetchone()[0] is not None else "MISSING"),
                              flush=True)
            print("CHECK: readiness HTTP " + str(initial.status_code), flush=True)
        check_response(client, 200)
        print("PASS: initial readiness 200; trading disabled", flush=True)
        stopped = False
        try:
            STAGE = "isolated Docker stop"
            check_identity(container_id)
            docker("stop", "--time", "10", "playgo-phase7d-db", timeout=30)
            stopped = True
            STAGE = "database outage detection"
            wait_until(lambda: not db_ready(dsn), 30,
                       "Isolated database outage")
            STAGE = "HTTP 503 outage readiness"
            check_response(client, 503)
            print("PASS: database outage readiness 503; fail closed", flush=True)
            STAGE = "independent liveness"
            live = client.get("/api/health")
            if (live.status_code != 200 or live.json().get("eligible") is not False
                    or live.json().get("execution") != "DISABLED"):
                raise AssertionError("Liveness incorrectly implies execution readiness")
            print("PASS: liveness remains independent and non-eligible", flush=True)
        finally:
            if stopped:
                STAGE = "isolated Docker restoration"
                check_identity(container_id)
                docker("start", "playgo-phase7d-db", timeout=30)
                print("RESTORE: isolated PostgreSQL container start requested", flush=True)
        STAGE = "database recovery connection"
        wait_until(lambda: db_ready(dsn), 90, "Isolated database recovery")
        STAGE = "HTTP readiness recovery"
        deadline = time.monotonic() + 30
        while True:
            response = client.get("/api/ready")
            if response.status_code == 200:
                check_response(client, 200)
                break
            if response.status_code != 503 or time.monotonic() >= deadline:
                raise AssertionError("Readiness did not recover within deadline")
            time.sleep(2)
        print("PASS: recovered readiness 200; trading disabled", flush=True)
        print("Phase 7G.3: ALL CHECKS PASSED", flush=True)


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, AssertionError, OSError) as exc:
        # Never print exception details; a connection error may contain secrets.
        print(f"FAIL: isolated readiness outage test failed at stage: {STAGE}", file=sys.stderr)
        sys.exit(1)
