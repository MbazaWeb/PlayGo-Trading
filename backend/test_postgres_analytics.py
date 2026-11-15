"""Offline Phase 5 analytics contract tests."""
import unittest
from unittest.mock import MagicMock, patch

from fastapi import HTTPException
import postgres_analytics
import postgres_api


class AnalyticsTests(unittest.TestCase):
    def test_snapshot_counts_orders_without_inventing_profit(self):
        conn = MagicMock()
        cur = conn.cursor.return_value.__enter__.return_value
        cur.fetchall.return_value = [
            ("FILLED", "EURUSD", 3), ("FILLED", "GBPUSD", 2),
            ("PENDING", "EURUSD", 1),
        ]
        state = {"balance": 10000.0, "starting_balance": 10000.0,
                 "revision": 2, "ticks": 5, "paused": False,
                 "feed_type": "SYNTHETIC", "positions": [], "trades": [],
                 "risk_lock_reason": None}
        with patch.object(postgres_analytics.postgres_state, "load", return_value=state):
            result = postgres_analytics.snapshot(conn)
        self.assertEqual(result["demo_orders"]["total"], 6)
        self.assertEqual(result["demo_orders"]["by_status"]["FILLED"], 5)
        self.assertEqual(result["demo_orders"]["by_pair"]["EURUSD"], 4)
        self.assertIsNone(result["performance"]["realized_pnl"])
        self.assertIsNone(result["performance"]["win_rate"])
        self.assertIsNone(result["performance"]["equity_curve"])
        self.assertEqual(result["paper"]["balance"], 10000.0)
        self.assertEqual(cur.execute.call_args.args[1], ("demo_order_intents",))

    def test_zero_orders(self):
        conn = MagicMock()
        conn.cursor.return_value.__enter__.return_value.fetchall.return_value = []
        with patch.object(postgres_analytics.postgres_state, "load", return_value={
            "balance": 10000, "starting_balance": 10000, "revision": 0,
            "positions": [], "trades": []}):
            result = postgres_analytics.snapshot(conn)
        self.assertEqual(result["demo_orders"]["total"], 0)
        self.assertEqual(result["demo_orders"]["by_pair"], {})

    def test_analytics_owner_only(self):
        with patch.object(postgres_api, "owner", side_effect=HTTPException(401, "Unauthorized")):
            with self.assertRaises(HTTPException) as caught:
                postgres_api.analytics_overview(authorization="")
        self.assertEqual(caught.exception.status_code, 401)

    def test_analytics_returns_snapshot(self):
        with patch.object(postgres_api, "owner", return_value="owner"), patch.object(
            postgres_api, "connect"
        ), patch.object(postgres_api.postgres_analytics, "snapshot",
                        return_value={"mode": "PAPER"}) as snapshot:
            result = postgres_api.analytics_overview(authorization="Bearer test")
        self.assertEqual(result["mode"], "PAPER")
        snapshot.assert_called_once()


if __name__ == "__main__":
    unittest.main()
