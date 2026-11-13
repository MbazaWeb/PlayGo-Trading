"""Optional single-process scheduled simulation worker.

Run separately from uvicorn: python worker.py
The API must run on the same machine (local-only mutation guard).
Never run multiple workers against the shared single-document paper account.
"""
from pathlib import Path
import json
import os
import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
API = os.getenv("PAPER_API_URL", "http://127.0.0.1:8000").rstrip("/")
INTERVAL = max(30, int(os.getenv("PAPER_CYCLE_SECONDS", "60")))

def run_once():
    request = Request(API + "/api/auto-cycle", data=b"{}", method="POST",
                      headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=20) as response:
        return json.load(response)

if __name__ == "__main__":
    target = urlsplit(API)
    if target.scheme != "http" or target.hostname not in ("127.0.0.1", "localhost") or target.username or target.password:
        raise SystemExit("Phase 2 worker requires an HTTP loopback backend")
    if os.getenv("PAPER_WORKER_ENABLED", "false").lower() != "true":
        raise SystemExit("Worker is opt-in. Set PAPER_WORKER_ENABLED=true to enable scheduled paper cycles.")
    print(f"PlayGo paper worker started: {API}; cycle every {INTERVAL}s; no live orders", flush=True)
    while True:
        try:
            snapshot = run_once()
            print(f"equity={snapshot['equity']} paused={snapshot['paused']} feed={snapshot['feed']}", flush=True)
        except HTTPError as exc:
            if exc.code == 429:
                print("Cycle cooldown active; waiting until next interval", flush=True)
            else:
                print(f"Agent cycle HTTP failure ({exc.code}); no immediate retry", flush=True)
        except (URLError, TimeoutError, ValueError, KeyError) as exc:
            print(f"Agent cycle failed; no retry before next interval: {type(exc).__name__}", flush=True)
        time.sleep(INTERVAL)
