"""Offline regression tests for PostgreSQL demo-order request validation."""
import unittest

from app.demo_execution import DemoExecutionEngine, DemoOrderError
from app.postgres_demo_orders import fingerprint


class DemoOrderValidationTests(unittest.TestCase):
    def test_same_request_same_fingerprint(self):
        args = ("EURUSD", "BUY", 100, "1.0849", "1.0851", "0.2")
        self.assertEqual(fingerprint(*args), fingerprint(*args))

    def test_slippage_is_part_of_idempotency_key(self):
        a = fingerprint("EURUSD", "BUY", 100, "1.0849", "1.0851", "0.2")
        b = fingerprint("EURUSD", "BUY", 100, "1.0849", "1.0851", "0.3")
        self.assertNotEqual(a, b)

    def test_fill_is_deterministic(self):
        kwargs = {"client_order_id": "order-1", "pair": "EURUSD", "side": "BUY",
                  "units": 100, "bid": "1.0849", "ask": "1.0851"}
        self.assertEqual(
            DemoExecutionEngine("0.2").execute(**kwargs)["execution_id"],
            DemoExecutionEngine("0.2").execute(**kwargs)["execution_id"])

    def test_invalid_pair_rejected(self):
        with self.assertRaises(DemoOrderError):
            DemoExecutionEngine().execute(
                client_order_id="x", pair="USDJPY", side="BUY",
                units=100, bid="150.1", ask="150.2")


if __name__ == "__main__":
    unittest.main()
