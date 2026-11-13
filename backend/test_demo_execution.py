"""Demo fill and paper accounting checks; no broker connection."""
import unittest
from demo_execution import DemoExecutionEngine, DemoOrderError
from reconciliation import reconcile


class DemoExecutionTests(unittest.TestCase):
    def test_repeat_order_returns_same_fill(self):
        engine = DemoExecutionEngine("0.5")
        args = dict(client_order_id="demo-001", pair="EURUSD", side="BUY",
                    units=1000, bid="1.10000", ask="1.10020")
        first = engine.execute(**args)
        self.assertEqual(first, engine.execute(**args))
        self.assertEqual(first["filled_price"], "1.10025")
        self.assertEqual(first["estimated_spread_cost_usd"], "0.20")

    def test_reused_key_with_changed_order_rejected(self):
        engine = DemoExecutionEngine()
        args = dict(client_order_id="demo-001", pair="EURUSD", side="BUY",
                    units=1000, bid="1.10000", ask="1.10020")
        engine.execute(**args)
        with self.assertRaises(DemoOrderError):
            engine.execute(**{**args, "units": 2000})

    def test_invalid_quotes_rejected(self):
        with self.assertRaises(DemoOrderError):
            DemoExecutionEngine().execute(client_order_id="x", pair="EURUSD",
                side="SELL", units=10, bid="1.1002", ask="1.1000")

    def test_reconciliation_detects_balance_mismatch(self):
        result = reconcile([], [{"id": "a", "pnl": 10}], 10000, 10000)
        self.assertFalse(result["consistent"])
        self.assertEqual(result["issues"][0]["code"], "BALANCE_MISMATCH")

    def test_reconciliation_passes_balanced_paper_account(self):
        result = reconcile([], [{"id": "a", "pnl": -5}], 9995, 10000)
        self.assertTrue(result["consistent"])


if __name__ == "__main__":
    unittest.main()
