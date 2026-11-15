"""No-database tests for safe PostgreSQL paper-state transitions."""
import unittest
from unittest.mock import patch

import postgres_state


class StateTests(unittest.TestCase):
    def setUp(self):
        self.previous = postgres_state.initial_state()

    def test_initial_state_is_paused_and_synthetic(self):
        self.assertTrue(self.previous["paused"])
        self.assertEqual(self.previous["feed_type"], "SYNTHETIC")
        self.assertEqual(self.previous["revision"], 0)

    def test_rejects_real_feed(self):
        proposed = dict(self.previous, feed_type="LIVE")
        with self.assertRaises(ValueError):
            postgres_state.commit(None, self.previous, proposed)

    def test_rejects_balance_reset(self):
        proposed = dict(self.previous, starting_balance=50000)
        with self.assertRaises(ValueError):
            postgres_state.commit(None, self.previous, proposed)

    def test_rejects_trade_history_rewrite(self):
        old = dict(self.previous, trades=[{"id": "a", "pnl": 10}])
        new = dict(old, trades=[{"id": "a", "pnl": 100}])
        with self.assertRaises(ValueError):
            postgres_state.commit(None, old, new)

    def test_rejects_stale_revision_input(self):
        proposed = dict(self.previous, revision=5)
        with self.assertRaises(ValueError):
            postgres_state.commit(None, self.previous, proposed)

    @patch("postgres_state.postgres_ledger.commit_state", return_value=1)
    def test_valid_state_delegates_to_atomic_ledger(self, mocked):
        result = postgres_state.commit(None, self.previous, dict(self.previous))
        self.assertEqual(result, 1)
        mocked.assert_called_once()


if __name__ == "__main__":
    unittest.main()
