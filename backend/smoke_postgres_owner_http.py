"""Owner-authenticated HTTP end-to-end checks against the dedicated TEST project.

Requires DATABASE_URL and PLAYGO_TEST_PROJECT_REF; prompts for existing owner
credentials. Does not bootstrap an owner, execute broker trades, or print secrets.
A uniquely identified DEMO order is persisted in the TEST database.
"""
import getpass
import json
import os
import subprocess
import sys
import time
from uuid import uuid4
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from psycopg.conninfo import conninfo_to_dict

PROJECT = "bkxapdsnpucrqptupzbz"
BASE = "http://127.0.0.1:18082"


def check_database_target():
    params = conninfo_to_dict(os.environ.get("DATABASE_URL", ""))
    host = params.get("host", "").lower()
    user = params.get("user", "")
    direct = host == f"db.{PROJECT}.supabase.co" and user == "postgres"
    pooler = (host.endswith(".pooler.supabase.com")
              and host.count(".") == 3
              and user == f"postgres.{PROJECT}"
              and str(params.get("port", "5432")) == "5432")
    if (os.getenv("PLAYGO_TEST_PROJECT_REF") != PROJECT
            or params.get("dbname") != "postgres"
            or not (direct or pooler)):
        raise RuntimeError("Refusing to run outside dedicated Supabase TEST project")


def call(path, *, method="GET", data=None, token=None):
    payload = json.dumps(data).encode() if data is not None else None
    req = Request(BASE + path, data=payload, method=method)
    if payload is not None:
        req.add_header("Content-Type", "application/json")
    if token is not None:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urlopen(req, timeout=20) as response:
            return response.status, json.load(response)
    except HTTPError as exc:
        return exc.code, json.load(exc)


def expect(status, expected, label):
    if status != expected:
        raise AssertionError(f"{label}: expected HTTP {expected}, got {status}")
    print(f"PASS: {label}")


def main():
    check_database_target()
    username = input("Existing TEST owner username: ").strip()
    password = getpass.getpass("Existing TEST owner password: ")
    if not username or not password:
        raise RuntimeError("Owner credentials required; no bootstrap performed")
    env = os.environ.copy()
    env["PLAYGO_ENV"] = "test"
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "postgres_api:app",
         "--host", "127.0.0.1", "--port", "18082", "--log-level", "error"],
        env=env,
    )
    try:
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError("API failed during startup")
            try:
                status, _ = call("/api/health")
                break
            except (URLError, TimeoutError):
                time.sleep(0.5)
        else:
            raise RuntimeError("API startup timeout")
        expect(status, 200, "PostgreSQL API started")
        status, result = call("/api/identity/login", method="POST",
                              data={"username": username, "password": password})
        if status == 401:
            raise RuntimeError("Owner login rejected: verify existing TEST owner; no account created")
        expect(status, 200, "owner login")
        token = result.get("access_token")
        if not isinstance(token, str) or len(token) != 64:
            raise AssertionError("Invalid owner bearer token")
        status, account = call("/api/identity/me/paper-account", token=token)
        expect(status, 200, "session authentication")
        assert account["mode"] == "PAPER" and account["role"] == "OWNER"
        status, state = call("/api/state", token=token)
        expect(status, 200, "persisted paper account state")
        assert state["mode"] == "PAPER" and isinstance(state["state"]["revision"], int)
        order = {"client_order_id": "http-e2e-" + uuid4().hex,
                 "pair": "EURUSD", "side": "BUY", "units": 1000,
                 "bid": "1.08500", "ask": "1.08512", "slippage_pips": "0.2"}
        status, placed = call("/api/demo/orders", method="POST", data=order, token=token)
        expect(status, 200, "demo order submission")
        assert placed["mode"] == "DEMO" and placed["status"] == "FILLED"
        status, replay = call("/api/demo/orders", method="POST", data=order, token=token)
        expect(status, 200, "demo order idempotent replay")
        assert replay["client_order_id"] == placed["client_order_id"]
        status, conflict = call("/api/demo/orders", method="POST",
                                data={**order, "units": 2000}, token=token)
        expect(status, 409, "conflicting demo order rejected")
        status, reconciliation = call("/api/accounting/reconciliation", token=token)
        expect(status, 200, "accounting reconciliation endpoint")
        if not reconciliation.get("consistent"):
            raise AssertionError("TEST accounting reconciliation inconsistent")
        print("PASS: accounting journal balances consistent")
        status, _ = call("/api/identity/logout", method="POST", token=token)
        expect(status, 200, "owner logout")
        status, _ = call("/api/state", token=token)
        expect(status, 401, "revoked session rejected")
        print("All authenticated HTTP checks passed; no live trading performed.")
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


if __name__ == "__main__":
    main()
