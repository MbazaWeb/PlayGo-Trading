"""Offline safety tests for PostgreSQL demo-order recovery."""

import unittest
from unittest.mock import MagicMock, patch

import psycopg

from app import postgres_demo_orders as orders


class PostgresRecoveryTests(unittest.TestCase):

    def setUp(self):
        self.conn = MagicMock()
        self.pending = [{
            "client_order_id": "recovery-001",
            "request": {
                "pair": "EURUSD",
                "side": "BUY",
                "units": 1000,
                "bid": "1.10000",
                "ask": "1.10020",
                "slippage_pips": "0.2",
            },
        }]

    @patch.object(orders, "submit_demo_order")
    @patch.object(orders, "pending_orders")
    def test_pending_order_recovered(self, mock_pending, mock_submit):
        mock_pending.return_value = self.pending
        mock_submit.return_value = {"status": "FILLED"}

        result = orders.recover_pending(self.conn)

        self.assertEqual(result["recovered"], ["recovery-001"])
        self.assertEqual(result["errors"], [])
        mock_submit.assert_called_once()

    @patch.object(orders, "submit_demo_order")
    @patch.object(orders, "pending_orders")
    def test_invalid_order_does_not_stop_recovery(
        self, mock_pending, mock_submit
    ):
        mock_pending.return_value = [
            self.pending[0],
            {
                **self.pending[0],
                "client_order_id": "recovery-002",
            },
        ]

        mock_submit.side_effect = [
            orders.DemoOrderError("Invalid order"),
            {"status": "FILLED"},
        ]

        result = orders.recover_pending(self.conn)

        self.assertEqual(result["recovered"], ["recovery-002"])
        self.assertEqual(
            result["errors"],
            [{
                "client_order_id": "recovery-001",
                "error": "DemoOrderError",
            }],
        )

    @patch.object(orders, "submit_demo_order")
    @patch.object(orders, "pending_orders")
    def test_database_failure_propagates(
        self, mock_pending, mock_submit
    ):
        mock_pending.return_value = self.pending
        mock_submit.side_effect = psycopg.OperationalError(
            "Database connection lost"
        )

        with self.assertRaises(psycopg.OperationalError):
            orders.recover_pending(self.conn)


if __name__ == "__main__":
    unittest.main()
