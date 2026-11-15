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


    @patch("postgres_state.commit", return_value=1)
    @patch("postgres_state.load")
    def test_pause_control_commits_revision(self, mocked_load, mocked_commit):
        mocked_load.return_value = dict(self.previous, paused=False)
        updated = postgres_state.set_paused(None, expected_revision=0, paused=True)
        self.assertTrue(updated["paused"])
        self.assertEqual(updated["revision"], 1)
        mocked_commit.assert_called_once()

    @patch("postgres_state.load")
    def test_pause_control_rejects_stale_revision(self, mocked_load):
        mocked_load.return_value = dict(self.previous, revision=3)
        with self.assertRaises(postgres_state.postgres_ledger.StaleStateError):
            postgres_state.set_paused(None, expected_revision=2, paused=True)

    @patch("postgres_state.load")
    def test_pause_control_cannot_override_risk_lock(self, mocked_load):
        mocked_load.return_value = dict(self.previous, risk_lock_reason="DAILY_DRAWDOWN")
        with self.assertRaises(ValueError):
            postgres_state.set_paused(None, expected_revision=0, paused=False)

    @patch("postgres_state.commit")
    @patch("postgres_state.load")
    def test_pause_control_is_idempotent(self, mocked_load, mocked_commit):
        mocked_load.return_value = dict(self.previous)
        updated = postgres_state.set_paused(None, expected_revision=0, paused=True)
        self.assertEqual(updated["revision"], 0)
        mocked_commit.assert_not_called()


    @patch("postgres_state.load")
    def test_unpause_rejects_daily_drawdown(self, mocked_load):
        from datetime import datetime, timezone
        mocked_load.return_value = dict(
            self.previous, paused=True, balance=9700.0,
            day_start_balance=10000.0,
            day_start_date=datetime.now(timezone.utc).date().isoformat())
        with self.assertRaisesRegex(ValueError, "drawdown"):
            postgres_state.set_paused(None, expected_revision=0, paused=False)

    @patch("postgres_state.load")
    def test_unpause_rejects_stale_utc_session(self, mocked_load):
        mocked_load.return_value = dict(
            self.previous, paused=True, day_start_date="2000-01-01")
        with self.assertRaisesRegex(ValueError, "UTC session"):
            postgres_state.set_paused(None, expected_revision=0, paused=False)


if __name__ == "__main__":
    unittest.main()
