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
    if not API.startswith(("http://127.0.0.1:", "http://localhost:")):
        raise SystemExit("Phase 2 worker requires a local backend")
    print(f"PlayGo paper worker started: {API}; cycle every {INTERVAL}s; no live orders", flush=True)
    while True:
        try:
            snapshot = run_once()
            print(f"equity={snapshot['equity']} paused={snapshot['paused']} feed={snapshot['feed']}", flush=True)
        except (HTTPError, URLError, TimeoutError, ValueError, KeyError) as exc:
            print(f"Agent cycle failed; no retry before next interval: {type(exc).__name__}", flush=True)
        time.sleep(INTERVAL)
