"""Phase 7D risk audit HTTP contract tests, with mocked persistence."""
from contextlib import contextmanager
from unittest import TestCase
from unittest.mock import patch

from fastapi.testclient import TestClient

import postgres_api
import postgres_identity
import postgres_risk_audit


@contextmanager
def fake_connection():
    yield object()


class RiskAuditApiTests(TestCase):
    def setUp(self):
        self.client = TestClient(postgres_api.app)
        self.headers = {"Authorization": "Bearer test-owner-session"}
        self.proposal = {"pair": "EURUSD", "side": "BUY", "units": 1000,
                         "entry_price": "1.085", "stop_loss": "1.080"}
        self.payload = {"assessment_id": "audit_001", "proposal": self.proposal}
        self.result = {"assessment_id": "audit_001", "mode": "PAPER",
                       "execution": "OBSERVATION_ONLY",
                       "state_revision": 3,
                       "decision": {"eligible": False,
                                    "reasons": ["AUTOMATION_DISABLED"]}}
        self.patches = [
            patch.object(postgres_api, "connect", side_effect=fake_connection),
            patch.object(postgres_identity, "verify_session",
                         side_effect=self._verify),
        ]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    @staticmethod
    def _verify(conn, authorization):
        if authorization != "Bearer test-owner-session":
            raise postgres_identity.OwnerAuthError("Invalid session")
        return "test-owner"

    def test_unauthorized_requests_never_reach_store(self):
        with patch.object(postgres_risk_audit, "record") as record, \
             patch.object(postgres_risk_audit, "get") as get, \
             patch.object(postgres_risk_audit, "list_recent") as listing:
            self.assertEqual(self.client.post(
                "/api/paper/automation/risk-assessments",
                json=self.payload).status_code, 401)
            self.assertEqual(self.client.get(
                "/api/paper/automation/risk-assessments").status_code, 401)
            self.assertEqual(self.client.get(
                "/api/paper/automation/risk-assessments/audit_001").status_code, 401)
            record.assert_not_called()
            get.assert_not_called()
            listing.assert_not_called()

    def test_record_and_identical_retry(self):
        with patch.object(postgres_risk_audit, "record",
                          return_value=self.result) as record, \
             patch.object(postgres_api.postgres_position_lifecycle,
                          "open_position") as opening:
            for _ in range(2):
                response = self.client.post(
                    "/api/paper/automation/risk-assessments",
                    json=self.payload, headers=self.headers)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), self.result)
            self.assertEqual(record.call_count, 2)
            record.assert_called_with(
                record.call_args.args[0],
                assessment_id="audit_001", proposal=self.proposal)
            opening.assert_not_called()

    def test_conflict_returns_409(self):
        with patch.object(postgres_risk_audit, "record",
                          side_effect=postgres_risk_audit.AuditConflict("conflict")):
            response = self.client.post(
                "/api/paper/automation/risk-assessments",
                json=self.payload, headers=self.headers)
            self.assertEqual(response.status_code, 409)

    def test_history_and_detail(self):
        history = {"total": 1, "assessments": [self.result]}
        with patch.object(postgres_risk_audit, "list_recent",
                          return_value=history), \
             patch.object(postgres_risk_audit, "get",
                          return_value=self.result):
            self.assertEqual(self.client.get(
                "/api/paper/automation/risk-assessments?limit=10",
                headers=self.headers).json(), history)
            self.assertEqual(self.client.get(
                "/api/paper/automation/risk-assessments/audit_001",
                headers=self.headers).json(), self.result)

    def test_missing_assessment_returns_404(self):
        with patch.object(postgres_risk_audit, "get", return_value=None):
            self.assertEqual(self.client.get(
                "/api/paper/automation/risk-assessments/missing",
                headers=self.headers).status_code, 404)

    def test_invalid_request_returns_422(self):
        with patch.object(postgres_risk_audit, "record") as record:
            self.assertEqual(self.client.post(
                "/api/paper/automation/risk-assessments",
                json={"assessment_id": "audit_001"},
                headers=self.headers).status_code, 422)
            record.assert_not_called()

    def test_invalid_history_pagination_returns_400(self):
        with patch.object(postgres_risk_audit, "list_recent",
                          side_effect=ValueError("Invalid limit")):
            self.assertEqual(self.client.get(
                "/api/paper/automation/risk-assessments?limit=0",
                headers=self.headers).status_code, 400)


if __name__ == "__main__":
    import unittest
    unittest.main()
