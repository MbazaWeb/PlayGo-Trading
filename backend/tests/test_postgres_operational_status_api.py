"""Phase 7E operational-status HTTP contract tests; no database writes."""
from contextlib import contextmanager
from unittest import TestCase
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import postgres_api
from app import postgres_identity
from app import postgres_state
from app import postgres_operational_monitor


@contextmanager
def fake_connection():
    yield object()


class OperationalStatusTests(TestCase):
    def setUp(self):
        self.client = TestClient(postgres_api.app)
        self.headers = {"Authorization": "Bearer test-owner"}
        self.state = postgres_state.initial_state()
        self.state["revision"] = 4
        self.accounting = {"consistent": True,
                           "balances_cents": {"CASH": 1000000}}
        self.auth = patch.object(postgres_identity, "verify_session",
                                 side_effect=self.verify)
        self.connect = patch.object(postgres_api, "connect",
                                    side_effect=fake_connection)
        self.load = patch.object(postgres_api.postgres_state, "load",
                                 return_value=self.state)
        self.reconcile = patch.object(postgres_api.postgres_accounting,
                                      "reconcile", return_value=self.accounting)
        for name in ("auth", "connect", "load", "reconcile"):
            patcher = getattr(self, name)
            mock = patcher.start()
            self.addCleanup(patcher.stop)
            setattr(self, name, mock)

    @staticmethod
    def verify(conn, authorization):
        if authorization != "Bearer test-owner":
            raise postgres_identity.OwnerAuthError("Invalid session")
        return "owner"

    def get(self, headers=None):
        return self.client.get(
            "/api/paper/automation/operational-status", headers=headers or {})

    def test_requires_owner(self):
        response = self.get()
        self.assertEqual(response.status_code, 401)
        self.load.assert_not_called()

    def test_healthy_still_disables_automation(self):
        response = self.get(self.headers)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["database"], "CONNECTED")
        self.assertEqual(data["execution"], "OBSERVATION_ONLY")
        self.assertFalse(data["automation_enabled"])
        self.assertFalse(data["eligible"])
        self.assertEqual(data["state_revision"], 4)
        self.assertIn("AUTOMATION_DISABLED", data["risk_reasons"])

    def test_emergency_stop_is_reported(self):
        self.state["automation_emergency_stop"] = True
        response = self.get(self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["emergency_stop"])
        self.assertIn("EMERGENCY_STOP", response.json()["risk_reasons"])

    def test_accounting_inconsistency_is_reported(self):
        self.accounting["consistent"] = False
        response = self.get(self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["accounting_consistent"])
        self.assertIn("ACCOUNTING_INCONSISTENT", response.json()["risk_reasons"])

    def test_outage_streak_and_recovery_are_sanitized(self):
        with patch.object(postgres_operational_monitor, "_state", {
            "consecutive_failures": 0,
            "last_failure_at": None,
            "last_recovery_at": None,
            "last_failure_category": None,
        }):
            self.load.side_effect = RuntimeError("secret password=hidden")
            for expected in (1, 2):
                response = self.get(self.headers)
                self.assertEqual(response.status_code, 503)
                self.assertEqual(
                    response.json()["detail"]["monitor"]["consecutive_failures"],
                    expected,
                )
                self.assertNotIn("password", response.text)
            self.load.side_effect = None
            response = self.get(self.headers)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                response.json()["monitor"]["consecutive_failures"], 0)
            self.assertIsNotNone(
                response.json()["monitor"]["last_recovery_at"])

    def test_invalid_failure_category_is_normalized(self):
        with patch.object(postgres_operational_monitor, "_state", {
            "consecutive_failures": 0,
            "last_failure_at": None,
            "last_recovery_at": None,
            "last_failure_category": None,
        }):
            postgres_operational_monitor.record_failure("password=secret")
            snapshot = postgres_operational_monitor.snapshot()
            self.assertEqual(snapshot["last_failure_category"], "DATABASE_ERROR")
            self.assertNotIn("secret", str(snapshot))

    def test_database_failure_fails_closed(self):
        self.load.side_effect = RuntimeError("secret DSN and details")
        response = self.get(self.headers)
        self.assertEqual(response.status_code, 503)
        data = response.json()["detail"]
        self.assertEqual(data["execution"], "DISABLED")
        self.assertFalse(data["eligible"])
        self.assertNotIn("secret", response.text)


if __name__ == "__main__":
    import unittest
    unittest.main()
