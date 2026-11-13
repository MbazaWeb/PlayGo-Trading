"""Read-only practice feed parser tests. No external API credentials or network."""
import json
import os
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch
import unittest

import feed

class FakeResponse:
    def __init__(self, payload):
        self.payload = payload
    def __enter__(self):
        return self
    def __exit__(self, *_args):
        return False
    def read(self, *_args):
        return json.dumps(self.payload).encode()

class FeedTests(unittest.TestCase):
    def test_missing_credentials_rejected(self):
        with patch.dict(os.environ, {"OANDA_API_TOKEN": "", "OANDA_ACCOUNT_ID": ""}):
            with self.assertRaises(feed.FeedUnavailable):
                feed.practice_quotes()

    def test_fresh_bid_ask_accepted(self):
        now = datetime.now(timezone.utc)
        payload = {"prices": [
            {"instrument": p, "status": "tradeable", "time": now.isoformat(),
             "bids": [{"price": bid}], "asks": [{"price": ask}]}
            for p,bid,ask in [("EUR_USD","1.10000","1.10013"),("GBP_USD","1.25000","1.25018")]
        ]}
        with patch.dict(os.environ, {"OANDA_API_TOKEN": "fake", "OANDA_ACCOUNT_ID": "fake"}), \
             patch.object(feed, "urlopen", return_value=FakeResponse(payload)):
            quotes = feed.practice_quotes(now=now)
        self.assertEqual(quotes["EURUSD"]["bid"], 1.1)
        self.assertEqual(quotes["GBPUSD"]["source"], "OANDA_PRACTICE")

    def test_stale_quotes_fail_closed(self):
        now = datetime.now(timezone.utc)
        old = (now - timedelta(minutes=5)).isoformat()
        payload = {"prices": [{"instrument": "EUR_USD", "status": "tradeable",
                    "time": old, "bids":[{"price":"1.1"}],"asks":[{"price":"1.1002"}]}]}
        with patch.dict(os.environ, {"OANDA_API_TOKEN": "fake", "OANDA_ACCOUNT_ID": "fake"}), \
             patch.object(feed, "urlopen", return_value=FakeResponse(payload)):
            with self.assertRaises(feed.FeedUnavailable):
                feed.practice_quotes(pairs=("EURUSD",), now=now)

if __name__ == "__main__":
    unittest.main()
