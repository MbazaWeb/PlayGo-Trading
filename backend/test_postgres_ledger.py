"""Unit tests for PostgreSQL paper-ledger event selection (no database required)."""
import unittest

from postgres_ledger import closed_trade_events


class PostgresLedgerTests(unittest.TestCase):
    def test_only_newly_closed_trades_create_events(self):
        previous = {"trades": [{"id": "t1", "pnl": 5}], "revision": 2}
        current = {"trades": [{"id": "t1", "pnl": 5}, {"id": "t2", "pnl": -2}]}
        events = closed_trade_events(previous, current)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["event_id"], "CLOSED:t2")
        self.assertEqual(events[0]["payload"]["trade"]["pnl"], -2)

    def test_duplicate_trade_ids_do_not_duplicate_events(self):
        events = closed_trade_events({}, {"trades": [{"id": "t3"}, {"id": "t3"}]})
        self.assertEqual(len(events), 1)

    def test_event_payload_is_copied(self):
        current = {"trades": [{"id": "t4", "meta": {"x": 1}}]}
        events = closed_trade_events({}, current)
        current["trades"][0]["meta"]["x"] = 2
        self.assertEqual(events[0]["payload"]["trade"]["meta"]["x"], 1)


if __name__ == "__main__":
    unittest.main()
