"""Opt-in automated Phase 7E.3 Docker outage/recovery test.

Windows PowerShell: run with the existing Python venv and WSL Docker.
Only the exact disposable local container is controlled. Never production.
"""
import json
import os
import subprocess
import sys
import time
from unittest.mock import patch

import psycopg
from psycopg.conninfo import conninfo_to_dict
from fastapi.testclient import TestClient

import postgres_api
import postgres_operational_monitor

NAME = "playgo-phase7d-db"
DB = "playgo_phase7d_isolated"
EXPECTED_IMAGE = "postgres:16"


def docker(*args, timeout=25, check=True):
    # On Windows, Docker CLI is installed inside Ubuntu WSL.
    prefix = ["wsl.exe", "-d", "Ubuntu", "--", "docker"] if os.name == "nt" else ["docker"]
    result = subprocess.run(
        [*prefix, *args], capture_output=True, text=True, timeout=timeout,
        check=False,
    )
    if check and result.returncode:
        raise RuntimeError("Isolated Docker operation failed: " + args[0])
    return result


def validate():
    if os.getenv("PLAYGO_RUN_ISOLATED_OUTAGE_TEST") != "1":
        raise SystemExit("Opt in with PLAYGO_RUN_ISOLATED_OUTAGE_TEST=1")
    dsn = os.getenv("PLAYGO_ISOLATED_DATABASE_URL", "")
    try:
        params = conninfo_to_dict(dsn)
    except psycopg.Error as exc:
        raise SystemExit("Invalid isolated DSN") from exc
    if (params.get("dbname") != DB
            or params.get("host") not in ("127.0.0.1", "localhost", "::1")
            or params.get("hostaddr")
            or os.getenv("DATABASE_URL") == dsn):
        raise SystemExit("Refusing non-isolated PostgreSQL DSN")
    info = json.loads(docker("inspect", NAME).stdout)[0]
    if (info["Name"] != "/" + NAME
            or info["Config"]["Image"] != EXPECTED_IMAGE
            or info["HostConfig"]["PortBindings"].get("5432/tcp")
            != [{"HostIp": "127.0.0.1", "HostPort": "5432"}]):
        raise SystemExit("Refusing unexpected Docker container/image/port binding")
    if not info["State"]["Running"]:
        raise SystemExit("Start isolated container before test")
    return dsn, info["Id"]


def check_identity(container_id):
    info = json.loads(docker("inspect", NAME).stdout)[0]
    if info["Id"] != container_id:
        raise RuntimeError("Isolated container identity changed; refusing action")


def db_ready(dsn):
    try:
        with psycopg.connect(dsn, connect_timeout=2) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT to_regclass('playgo_private.documents')")
                return cur.fetchone()[0] is not None
    except psycopg.Error:
        return False


def wait_until(predicate, seconds, description):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(1)
    raise AssertionError(description + " timed out")


def probe(client):
    response = client.get(
        "/api/paper/automation/operational-status",
        headers={"Authorization": "Bearer isolated-test"},
    )
    return response.status_code, response.json()


def main():
    dsn, container_id = validate()
    wait_until(lambda: db_ready(dsn), 30, "Initial Windows PostgreSQL connectivity")
    # Never touch a running database unless the isolated name, image,
    # port binding and database identity have all been checked.
    with patch.object(postgres_api, "connect",
                      side_effect=lambda: psycopg.connect(dsn, connect_timeout=2)), \
         patch.object(postgres_api, "owner", return_value="isolated-test"), \
         patch.object(postgres_operational_monitor, "_state", {
             "consecutive_failures": 0, "last_failure_at": None,
             "last_recovery_at": None, "last_failure_category": None,
         }):
        client = TestClient(postgres_api.app)
        code, body = probe(client)
        if code != 200 or body.get("eligible") is not False:
            raise AssertionError("Initial status must be healthy and disabled")
        print("PASS: initial status healthy; execution disabled", flush=True)
        try:
            check_identity(container_id)
            docker("stop", "--time", "10", NAME, timeout=30)
            wait_until(lambda: not db_ready(dsn), 30,
                       "Windows-side PostgreSQL disconnection")
            for expected in (1, 2):
                code, body = probe(client)
                detail = body.get("detail", {})
                if (code != 503 or detail.get("eligible") is not False
                        or detail.get("execution") != "DISABLED"
                        or detail.get("monitor", {}).get("consecutive_failures") != expected):
                    raise AssertionError("Outage HTTP/status check failed")
                print(f"PASS: outage HTTP 503, failure streak {expected}", flush=True)
        finally:
            # Always attempt restoration, even if assertions or connection
            # checks fail. Never start a different container with this name.
            check_identity(container_id)
            docker("start", NAME, timeout=30)
            print("RESTORE: isolated container start requested", flush=True)

        wait_until(lambda: db_ready(dsn), 90,
                   "Windows-side PostgreSQL recovery")
        deadline = time.monotonic() + 30
        while True:
            code, body = probe(client)
            if code == 200:
                break
            if code != 503 or time.monotonic() >= deadline:
                raise AssertionError("Recovery endpoint did not return HTTP 200")
            time.sleep(2)
        if (body.get("eligible") is not False
                or body.get("monitor", {}).get("consecutive_failures") != 0
                or body.get("monitor", {}).get("last_recovery_at") is None):
            raise AssertionError("Recovery safety/telemetry assertion failed")
        print("PASS: recovered; failure streak cleared; execution disabled")
        print("Phase 7E.3: ALL CHECKS PASSED")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, AssertionError, subprocess.TimeoutExpired) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        sys.exit(1)
