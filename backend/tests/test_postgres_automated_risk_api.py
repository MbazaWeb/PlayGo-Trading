"""Phase 7D risk-preview HTTP contract tests; no database access."""
from contextlib import contextmanager
from unittest import TestCase
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import postgres_api
from app import postgres_identity


class FakeConnection:
    @contextmanager
    def transaction(self):
        yield

    @contextmanager
    def cursor(self):
        yield self

    def execute(self, query):
        if query != "set transaction isolation level repeatable read, read only":
            raise AssertionError("Unexpected SQL statement")


@contextmanager
def fake_connection():
    yield FakeConnection()


class RiskPreviewApiTests(TestCase):
    def setUp(self):
        self.client = TestClient(postgres_api.app)
        self.headers = {"Authorization": "Bearer test-owner-session"}
        self.payload = {"pair": "EURUSD", "side": "BUY", "units": 1000,
                        "entry_price": "1.085", "stop_loss": "1.080"}
        self.state = {"revision": 4}
        self.accounting = {"consistent": True}
        self.decision = {"mode": "PAPER", "phase": "7D",
                         "execution": "OBSERVATION_ONLY", "eligible": False,
                         "reasons": ["AUTOMATION_DISABLED"]}
        self.patches = [
            patch.object(postgres_api, "connect", side_effect=fake_connection),
            patch.object(postgres_identity, "verify_session",
                         side_effect=self._verify),
            patch.object(postgres_api.postgres_state, "load",
                         return_value=self.state),
            patch.object(postgres_api.postgres_accounting, "reconcile",
                         return_value=self.accounting),
        ]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)

    @staticmethod
    def _verify(conn, authorization):
        if authorization != "Bearer test-owner-session":
            raise postgres_identity.OwnerAuthError("Invalid session")
        return "test-owner"

    def test_requires_owner_authentication(self):
        with patch.object(postgres_api.postgres_automated_risk, "assess") as assess:
            response = self.client.post("/api/paper/automation/risk-preview",
                                        json=self.payload)
            self.assertEqual(response.status_code, 401)
            assess.assert_not_called()

    def test_read_only_preview_forces_automation_disabled(self):
        with patch.object(postgres_api.postgres_automated_risk, "assess",
                          return_value=self.decision) as assess, \
             patch.object(postgres_api.postgres_position_lifecycle,
                          "open_position") as open_position:
            response = self.client.post("/api/paper/automation/risk-preview",
                                        json=self.payload, headers=self.headers)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["execution"], "OBSERVATION_ONLY")
            self.assertEqual(response.json()["state_revision"], 4)
            self.assertEqual(response.json()["decision"], self.decision)
            assess.assert_called_once_with(
                self.state, self.accounting, proposal=self.payload,
                automation_enabled=False)
            open_position.assert_not_called()

    def test_malformed_payload_rejected(self):
        with patch.object(postgres_api.postgres_automated_risk, "assess") as assess:
            response = self.client.post("/api/paper/automation/risk-preview",
                                        json={"pair": "EURUSD"},
                                        headers=self.headers)
            self.assertEqual(response.status_code, 422)
            assess.assert_not_called()


if __name__ == "__main__":
    import unittest
    unittest.main()
