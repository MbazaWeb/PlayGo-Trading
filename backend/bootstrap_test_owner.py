"""One-time loopback-only owner bootstrap for dedicated PlayGo Supabase TEST.

Requires DATABASE_URL and PLAYGO_TEST_PROJECT_REF in environment. Never prints
passwords, bearer tokens, or bootstrap secrets. No production target accepted.
"""
import getpass
import json
import os
import secrets
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from psycopg.conninfo import conninfo_to_dict

PROJECT = "bkxapdsnpucrqptupzbz"
URL = "http://127.0.0.1:18083"


def check_test_database():
    params = conninfo_to_dict(os.getenv("DATABASE_URL", ""))
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
        raise RuntimeError("Bootstrap refused: only dedicated Supabase TEST project permitted")


def call(path, data=None, secret=None):
    payload = json.dumps(data).encode() if data is not None else None
    request = Request(URL + path, data=payload, method="POST" if payload else "GET")
    if payload is not None:
        request.add_header("Content-Type", "application/json")
    if secret is not None:
        request.add_header("X-PlayGo-Bootstrap-Secret", secret)
    try:
        with urlopen(request, timeout=20) as response:
            return response.status, json.load(response)
    except HTTPError as exc:
        return exc.code, json.load(exc)


def main():
    check_test_database()
    username = "playgo_admin"
    password = getpass.getpass("Create NEW PlayGo TEST owner password (12+ chars): ")
    confirmation = getpass.getpass("Confirm new owner password: ")
    if password != confirmation or not 12 <= len(password) <= 256:
        raise RuntimeError("Passwords differ or length is outside 12-256 characters")
    secret = secrets.token_urlsafe(48)
    env = os.environ.copy()
    env["PLAYGO_ENV"] = "local"
    env["PLAYGO_OWNER_BOOTSTRAP_SECRET"] = secret
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "postgres_api:app",
         "--host", "127.0.0.1", "--port", "18083", "--log-level", "error"],
        env=env,
    )
    try:
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError("API exited during bootstrap startup")
            try:
                status, _ = call("/api/health")
                break
            except (URLError, TimeoutError):
                time.sleep(0.5)
        else:
            raise RuntimeError("API startup timeout")
        if status != 200:
            raise RuntimeError(f"API health failed: HTTP {status}")
        status, result = call("/api/identity/bootstrap-owner",
                              {"username": username, "password": password},
                              secret=secret)
        if status == 409:
            raise RuntimeError("Owner already exists in TEST database; bootstrap refused")
        if status != 200:
            raise RuntimeError(f"Owner bootstrap failed: HTTP {status} ({result.get('detail', 'unknown')})")
        if result.get("username") != username:
            raise RuntimeError("Unexpected owner bootstrap response")
        print("SUCCESS: playgo_admin owner created in Supabase TEST database")
        print("Next: run authenticated HTTP smoke tests with the password you just chose")
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


if __name__ == "__main__":
    main()
