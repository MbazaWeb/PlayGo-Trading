"""Read-only OANDA practice pricing adapter. Does not submit broker orders."""
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from urllib.parse import urlencode
import json
import os

class FeedUnavailable(RuntimeError):
    pass

def practice_quotes(pairs=("EURUSD", "GBPUSD"), now=None):
    token = os.getenv("OANDA_API_TOKEN")
    account = os.getenv("OANDA_ACCOUNT_ID")
    if not token or not account:
        raise FeedUnavailable("OANDA_API_TOKEN and OANDA_ACCOUNT_ID are required")
    instruments = ",".join(p[:3] + "_" + p[3:] for p in pairs)
    query = urlencode({"instruments": instruments})
    url = f"https://api-fxpractice.oanda.com/v3/accounts/{account}/pricing?{query}"
    request = Request(url, headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})
    try:
        with urlopen(request, timeout=8) as response:
            payload = json.load(response)
    except Exception as exc:
        raise FeedUnavailable("OANDA practice quote request failed") from exc
    now = now or datetime.now(timezone.utc)
    quotes = {}
    for item in payload.get("prices", []):
        pair = str(item.get("instrument", "")).replace("_", "")
        if pair not in pairs or item.get("status", "").lower() != "tradeable":
            continue
        try:
            timestamp = datetime.fromisoformat(item["time"].replace("Z", "+00:00"))
            age = (now - timestamp).total_seconds()
            if age < -10 or age > 120:
                continue
            bid = float(item["bids"][0]["price"])
            ask = float(item["asks"][0]["price"])
        except (KeyError, IndexError, TypeError, ValueError):
            continue
        if not (0 < bid < ask):
            continue
        pip = 0.01 if pair.endswith("JPY") else 0.0001
        quotes[pair] = {"bid": bid, "ask": ask, "pip": pip, "spread": ask - bid,
                        "timestamp": timestamp.isoformat(), "source": "OANDA_PRACTICE"}
    if len(quotes) != len(pairs):
        raise FeedUnavailable("Missing, stale or non-tradeable OANDA quote; aborting cycle")
    return quotes
