"""Phase 7D emergency-stop tests. No database writes."""
from contextlib import contextmanager
from unittest import TestCase
from unittest.mock import patch

from fastapi.testclient import TestClient

import postgres_api
import postgres_auto_controller
import postgres_identity
import postgres_ledger
import postgres_state


@contextmanager
def fake_connection():
    yield object()


class EmergencyStopTests(TestCase):
    def setUp(self):
        self.client = TestClient(postgres_api.app)
        self.headers = {"Authorization": "Bearer test-owner-session"}
        self.state = postgres_state.initial_state()
        self.state["paused"] = True
        self.state["automation_emergency_stop"] = True
        self.state["revision"] = 7
        self.connect_patch = patch.object(postgres_api, "connect",
                                          side_effect=fake_connection)
        self.auth_patch = patch.object(
            postgres_identity, "verify_session", side_effect=self._verify)
        self.connect_patch.start()
        self.auth_patch.start()
        self.addCleanup(self.connect_patch.stop)
        self.addCleanup(self.auth_patch.stop)

    @staticmethod
    def _verify(conn, authorization):
        if authorization != "Bearer test-owner-session":
            raise postgres_identity.OwnerAuthError("Invalid session")
        return "test-owner"

    def test_unauthorized_stop_does_not_mutate(self):
        with patch.object(postgres_api.postgres_emergency_stop, "engage") as stop:
            response = self.client.post(
                "/api/paper/automation/emergency-stop",
                json={"expected_revision": 7, "reason": "Operator requested"})
            self.assertEqual(response.status_code, 401)
            stop.assert_not_called()

    def test_authorized_stop_returns_disabled(self):
        with patch.object(postgres_api.postgres_emergency_stop, "engage",
                          return_value=self.state) as stop:
            response = self.client.post(
                "/api/paper/automation/emergency-stop",
                headers=self.headers,
                json={"expected_revision": 7, "reason": "Operator requested"})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["execution"], "DISABLED")
            self.assertTrue(response.json()["emergency_stop"])
            stop.assert_called_once()

    def test_stale_revision_is_conflict(self):
        with patch.object(postgres_api.postgres_emergency_stop, "engage",
                          side_effect=postgres_ledger.StaleStateError("stale")):
            response = self.client.post(
                "/api/paper/automation/emergency-stop",
                headers=self.headers,
                json={"expected_revision": 7, "reason": "Operator requested"})
            self.assertEqual(response.status_code, 409)

    def test_invalid_reason_is_bad_request(self):
        with patch.object(postgres_api.postgres_emergency_stop, "engage",
                          side_effect=ValueError("Invalid reason")):
            response = self.client.post(
                "/api/paper/automation/emergency-stop",
                headers=self.headers,
                json={"expected_revision": 7, "reason": "x"})
            self.assertEqual(response.status_code, 400)

    def test_latched_stop_blocks_automation_even_when_enabled(self):
        self.state["paused"] = False
        result = postgres_auto_controller.evaluate(
            self.state, {"consistent": True,
                         "balances_cents": {"CASH": 1000000}},
            automation_enabled=True)
        self.assertFalse(result["eligible"])
        self.assertIn("EMERGENCY_STOP", result["reasons"])

    def test_latched_stop_blocks_unpause(self):
        self.state["paused"] = True
        with patch.object(postgres_state, "load", return_value=self.state):
            with self.assertRaisesRegex(ValueError, "Emergency stop"):
                postgres_state.set_paused(
                    object(), expected_revision=7, paused=False)


if __name__ == "__main__":
    import unittest
    unittest.main()
