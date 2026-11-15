"""Unit tests for Phase 7A's observation-only automation gate."""
from copy import deepcopy
from datetime import datetime, timezone
import unittest

import postgres_auto_controller as controller
import postgres_state


class AutomationGateTests(unittest.TestCase):
    def setUp(self):
        self.state = postgres_state.initial_state()
        self.state["paused"] = False
        self.accounting = {
            "consistent": True,
            "balances_cents": {"CASH": 1_000_000},
        }

    def test_disabled_by_default(self):
        result = controller.evaluate(self.state, self.accounting)
        self.assertFalse(result["eligible"])
        self.assertIn("AUTOMATION_DISABLED", result["reasons"])
        self.assertEqual(result["execution"], "OBSERVATION_ONLY")

    def test_eligible_is_still_observation_only(self):
        original = deepcopy(self.state)
        result = controller.evaluate(self.state, self.accounting,
                                     automation_enabled=True)
        self.assertTrue(result["eligible"])
        self.assertEqual(result["execution"], "OBSERVATION_ONLY")
        self.assertEqual(self.state, original)

    def test_accounting_mismatch_rejected(self):
        account = deepcopy(self.accounting)
        account["balances_cents"]["CASH"] += 1
        result = controller.evaluate(self.state, account, automation_enabled=True)
        self.assertIn("CASH_MISMATCH", result["reasons"])

    def test_paused_or_risk_locked_rejected(self):
        self.state["paused"] = True
        self.state["risk_lock_reason"] = "LOSS_STREAK"
        result = controller.evaluate(self.state, self.accounting,
                                     automation_enabled=True)
        self.assertIn("ENGINE_PAUSED", result["reasons"])
        self.assertIn("RISK_LOCKED", result["reasons"])

    def test_stale_session_rejected(self):
        self.state["day_start_date"] = "2000-01-01"
        result = controller.evaluate(self.state, self.accounting,
                                     automation_enabled=True)
        self.assertIn("SESSION_ROLLOVER_REQUIRED", result["reasons"])

    def test_position_limit_rejected(self):
        self.state["positions"] = [
            {"entry_price": "1.1", "units": 1000},
            {"entry_price": "1.1", "units": 1000},
        ]
        result = controller.evaluate(self.state, self.accounting,
                                     automation_enabled=True)
        self.assertIn("AUTOMATION_POSITION_LIMIT", result["reasons"])


if __name__ == "__main__":
    unittest.main()
