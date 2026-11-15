"""Database-independent settlement validation regression tests."""
import unittest

from postgres_settlement import SettlementError, event_to_post


def event(trade_id, pnl):
    return {"_id": "CLOSED:" + trade_id, "trade_id": trade_id,
            "event_type": "PAPER_TRADE_CLOSED",
            "trade": {"id": trade_id, "pnl": pnl}}


class PostgresSettlementTests(unittest.TestCase):
    def test_gain(self):
        self.assertEqual(event_to_post(event("a", "12.34"))["amount_cents"], 1234)
        self.assertEqual(event_to_post(event("a", "12.34"))["kind"], "REALIZED_GAIN")

    def test_loss(self):
        self.assertEqual(event_to_post(event("a", "-1.25"))["kind"], "REALIZED_LOSS")

    def test_zero(self):
        self.assertIsNone(event_to_post(event("a", "0")))

    def test_fractional_cent_rejected(self):
        with self.assertRaises(SettlementError):
            event_to_post(event("a", "0.001"))

    def test_nan_rejected(self):
        with self.assertRaises(SettlementError):
            event_to_post(event("a", "NaN"))

    def test_mismatched_trade_id_rejected(self):
        bad = event("a", "1")
        bad["trade"]["id"] = "b"
        with self.assertRaises(SettlementError):
            event_to_post(bad)


if __name__ == "__main__":
    unittest.main()
