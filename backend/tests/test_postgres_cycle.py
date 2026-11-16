"""Offline synthetic-cycle safety regression tests."""
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from app import postgres_cycle
from app import postgres_state


class SyntheticCycleTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 15, 10, 0, tzinfo=timezone.utc)
        self.state = postgres_state.initial_state()

    def test_cycle_is_observation_only(self):
        updated = postgres_cycle.simulate_cycle(self.state, now=self.now)
        self.assertEqual(updated["ticks"], 1)
        self.assertEqual(updated["positions"], [])
        self.assertEqual(updated["trades"], [])
        self.assertEqual(updated["balance"], self.state["balance"])
        self.assertEqual(updated["feed_type"], "SYNTHETIC")

    def test_original_state_is_not_mutated(self):
        postgres_cycle.simulate_cycle(self.state, now=self.now)
        self.assertEqual(self.state["ticks"], 0)

    def test_cooldown_rejects_fast_repeat(self):
        self.state["last_cycle_at"] = (self.now - timedelta(seconds=5)).isoformat()
        with self.assertRaises(postgres_cycle.CycleCooldown):
            postgres_cycle.simulate_cycle(self.state, now=self.now)

    def test_non_synthetic_feed_rejected(self):
        self.state["feed_type"] = "LIVE"
        with self.assertRaises(ValueError):
            postgres_cycle.simulate_cycle(self.state, now=self.now)

    def test_utc_rollover_pauses(self):
        self.state["paused"] = False
        self.state["day_start_date"] = "2026-11-14"
        updated = postgres_cycle.simulate_cycle(self.state, now=self.now)
        self.assertTrue(updated["paused"])

    def test_utc_rollover_preserves_risk_lock(self):
        self.state["paused"] = False
        self.state["day_start_date"] = "2026-11-14"
        self.state["risk_lock_reason"] = "DAILY_DRAWDOWN"
        self.state["loss_streak"] = 3
        updated = postgres_cycle.simulate_cycle(self.state, now=self.now)
        self.assertTrue(updated["paused"])
        self.assertEqual(updated["risk_lock_reason"], "DAILY_DRAWDOWN")
        self.assertEqual(updated["loss_streak"], 3)

    @patch("app.postgres_cycle.postgres_state.commit", return_value=1)
    @patch("app.postgres_cycle.postgres_state.load")
    def test_run_cycle_uses_cas(self, load, commit):
        load.return_value = self.state
        updated = postgres_cycle.run_cycle(None, expected_revision=0)
        self.assertEqual(updated["revision"], 1)
        commit.assert_called_once()

    @patch("app.postgres_cycle.postgres_state.load")
    def test_stale_revision_rejected(self, load):
        load.return_value = dict(self.state, revision=2)
        with self.assertRaises(postgres_state.postgres_ledger.StaleStateError):
            postgres_cycle.run_cycle(None, expected_revision=1)


if __name__ == "__main__":
    unittest.main()
