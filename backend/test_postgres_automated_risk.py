"""Pure Phase 7D risk and irreversible emergency-stop invariant tests."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import unittest
from unittest.mock import patch

import postgres_automated_risk as risk
import postgres_positions
import postgres_state


class AutomatedRiskTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime.now(timezone.utc)
        self.state = postgres_state.initial_state()
        self.state["paused"] = False
        self.accounting = {"consistent": True,
                           "balances_cents": {"CASH": 1_000_000}}
        self.proposal = {"pair": "EURUSD", "side": "BUY", "units": 1000,
                         "entry_price": "1.085", "stop_loss": "1.080"}

    def assess(self):
        return risk.assess(self.state, self.accounting, proposal=self.proposal,
                           automation_enabled=True, now=self.now)

    def test_eligible_is_observation_only_and_pure(self):
        before = deepcopy(self.state)
        result = self.assess()
        self.assertTrue(result["eligible"], result["reasons"])
        self.assertEqual(result["execution"], "OBSERVATION_ONLY")
        self.assertEqual(self.state, before)

    def test_cooldown_rejects_recent_entry(self):
        self.state["last_automated_entry_at"] = (
            self.now - timedelta(seconds=60)).isoformat()
        self.assertIn("AUTOMATION_COOLDOWN", self.assess()["reasons"])

    def test_cooldown_allows_elapsed_window(self):
        self.state["last_automated_entry_at"] = (
            self.now - timedelta(seconds=120)).isoformat()
        self.assertTrue(self.assess()["eligible"])

    def test_malformed_cooldown_fails_closed(self):
        self.state["last_automated_entry_at"] = "not-a-date"
        self.assertIn("INVALID_COOLDOWN_TIMESTAMP", self.assess()["reasons"])

    def test_emergency_stop_rejects(self):
        self.state["automation_emergency_stop"] = True
        self.assertIn("EMERGENCY_STOP", self.assess()["reasons"])
        with self.assertRaisesRegex(postgres_positions.RiskRejected, "Emergency stop"):
            postgres_positions.validate_open(self.state, **self.proposal)

    def test_daily_drawdown_rejects(self):
        self.state["balance"] = 9800
        self.accounting["balances_cents"]["CASH"] = 980000
        self.assertIn("DAILY_DRAWDOWN", self.assess()["reasons"])

    def test_proposed_exposure_rejects(self):
        # 4,000 units alone fit the $5,000 manual position cap; together
        # with an existing 1,000-unit position they exceed the stricter
        # $5,000 automated total exposure cap.
        self.state["positions"] = [{"pair": "EURUSD", "side": "BUY",
                                    "units": 1000, "entry_price": "1.085",
                                    "stop_loss": "1.080"}]
        self.proposal["units"] = 4000
        self.assertIn("AUTOMATION_EXPOSURE_LIMIT", self.assess()["reasons"])

    def test_invalid_proposal_rejects(self):
        self.proposal = {}
        self.assertIn("POSITION_RISK_REJECTED", self.assess()["reasons"])

    def test_emergency_stop_cannot_be_cleared_by_commit(self):
        previous = deepcopy(self.state)
        previous["automation_emergency_stop"] = True
        previous["paused"] = True
        proposed = deepcopy(previous)
        proposed["automation_emergency_stop"] = False
        with self.assertRaisesRegex(ValueError, "cannot be cleared"):
            postgres_state.commit(object(), previous, proposed)

    def test_emergency_stop_cannot_be_unpaused_by_commit(self):
        previous = deepcopy(self.state)
        previous["automation_emergency_stop"] = True
        previous["paused"] = True
        proposed = deepcopy(previous)
        proposed["paused"] = False
        with self.assertRaisesRegex(ValueError, "remain paused"):
            postgres_state.commit(object(), previous, proposed)


if __name__ == "__main__":
    unittest.main()
