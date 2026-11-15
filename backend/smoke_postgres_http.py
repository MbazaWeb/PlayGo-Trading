"""HTTP smoke tests for the isolated PostgreSQL paper API.

Run only with DATABASE_URL set to the dedicated Supabase TEST database.
Starts a loopback-only Uvicorn process and never bootstraps an owner.
"""
import json
import os
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from psycopg.conninfo import conninfo_to_dict

PROJECT = "bkxapdsnpucrqptupzbz"
BASE = "http://127.0.0.1:18081"


def verify_target():
    dsn = os.getenv("DATABASE_URL", "")
    if not dsn:
        raise RuntimeError("DATABASE_URL missing")
    info = conninfo_to_dict(dsn)
    host = info.get("host", "").lower()
    user = info.get("user", "")
    if not (
        os.getenv("PLAYGO_TEST_PROJECT_REF") == PROJECT
        and info.get("dbname") == "postgres"
        and (
            (host == f"db.{PROJECT}.supabase.co" and user == "postgres")
            or (
                host.endswith(".pooler.supabase.com")
                and host.count(".") == 3
                and user == f"postgres.{PROJECT}"
                and str(info.get("port", "5432")) == "5432"
            )
        )
    ):
        raise RuntimeError("Refusing HTTP smoke tests outside dedicated Supabase TEST project")


def request(path, method="GET", payload=None):
    body = json.dumps(payload).encode() if payload is not None else None
    req = Request(BASE + path, data=body, method=method)
    if body is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urlopen(req, timeout=10) as response:
            return response.status, json.load(response)
    except HTTPError as exc:
        return exc.code, json.load(exc)


def main():
    verify_target()
    env = os.environ.copy()
    env["PLAYGO_ENV"] = "test"
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "postgres_api:app",
         "--host", "127.0.0.1", "--port", "18081", "--log-level", "error"],
        env=env,
    )
    try:
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError("API process exited during startup")
            try:
                status, body = request("/api/health")
                break
            except (URLError, TimeoutError):
                time.sleep(0.5)
        else:
            raise RuntimeError("API startup timeout")
        assert status == 200 and body == {
            "ok": True, "mode": "PAPER", "database": "POSTGRESQL"
        }, (status, body)
        print("PASS: HTTP health + PostgreSQL connectivity")
        status, _ = request("/api/identity/register", "POST", {})
        assert status == 403, status
        print("PASS: public registration disabled (403)")
        status, _ = request("/api/state")
        assert status == 401, status
        print("PASS: paper state requires owner session (401)")
        status, _ = request("/api/accounting/reconciliation")
        assert status == 401, status
        print("PASS: accounting requires owner session (401)")
        print("4 HTTP smoke checks passed; owner-authenticated flows remain untested.")
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


if __name__ == "__main__":
    main()
