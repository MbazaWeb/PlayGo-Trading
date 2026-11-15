"""Phase 7C HTTP contract tests; all persistence is mocked.

These tests exercise FastAPI routing/auth guards and response mapping without
accessing Supabase or creating trades. PostgreSQL concurrency is tested separately.
"""
from contextlib import contextmanager
from unittest import TestCase
from unittest.mock import patch

from fastapi.testclient import TestClient

import postgres_api
import postgres_identity
import postgres_signal_store


@contextmanager
def fake_connection():
    yield object()


class SignalApiTests(TestCase):
    def setUp(self):
        self.client = TestClient(postgres_api.app)
        self.signal = {
            "signal_id": "sig_api_001",
            "pair": "EURUSD", "side": "BUY",
            "confidence": "0.85",
            "timestamp": "2026-11-15T12:00:00+00:00",
            "stop_loss": "1.0800",
        }
        self.decision = {
            "mode": "PAPER", "execution": "VALIDATION_ONLY",
            "signal_id": "sig_api_001", "accepted": False,
            "reasons": ["SIGNAL_EXPIRED_OR_FUTURE"],
            "proposal": None, "recorded_at": "2026-11-15T12:00:01+00:00",
        }
        self.connect_patch = patch.object(postgres_api, "connect",
                                          side_effect=fake_connection)
        self.auth_patch = patch.object(
            postgres_identity, "verify_session",
            side_effect=self._verify)
        self.connect_patch.start()
        self.auth_patch.start()
        self.addCleanup(self.connect_patch.stop)
        self.addCleanup(self.auth_patch.stop)
        self.headers = {"Authorization": "Bearer test-owner-session"}

    @staticmethod
    def _verify(conn, authorization):
        if authorization != "Bearer test-owner-session":
            raise postgres_identity.OwnerAuthError("Invalid session")
        return "test-owner"

    def test_unauthenticated_requests_are_rejected_before_storage(self):
        with patch.object(postgres_signal_store, "record_signal") as write, \
             patch.object(postgres_signal_store, "list_signals") as history, \
             patch.object(postgres_signal_store, "get_signal") as detail:
            self.assertEqual(self.client.post(
                "/api/paper/signals", json=self.signal).status_code, 401)
            self.assertEqual(self.client.get("/api/paper/signals").status_code, 401)
            self.assertEqual(self.client.get(
                "/api/paper/signals/sig_api_001").status_code, 401)
            write.assert_not_called()
            history.assert_not_called()
            detail.assert_not_called()

    def test_authenticated_submission_is_validation_only(self):
        with patch.object(postgres_signal_store, "record_signal",
                          return_value=self.decision) as write, \
             patch.object(postgres_api.postgres_position_lifecycle,
                          "open_position") as open_position:
            response = self.client.post("/api/paper/signals",
                                        json=self.signal, headers=self.headers)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), self.decision)
            write.assert_called_once_with(
                write.call_args.args[0], signal=self.signal)
            open_position.assert_not_called()

    def test_duplicate_submission_returns_same_decision(self):
        with patch.object(postgres_signal_store, "record_signal",
                          return_value=self.decision) as write:
            first = self.client.post("/api/paper/signals", json=self.signal,
                                     headers=self.headers)
            second = self.client.post("/api/paper/signals", json=self.signal,
                                      headers=self.headers)
            self.assertEqual(first.status_code, 200)
            self.assertEqual(second.json(), first.json())
            self.assertEqual(write.call_count, 2)

    def test_conflicting_id_returns_409(self):
        with patch.object(postgres_signal_store, "record_signal",
                          side_effect=postgres_signal_store.SignalConflict(
                              "Signal ID reused with different payload")):
            response = self.client.post("/api/paper/signals",
                                        json=self.signal, headers=self.headers)
            self.assertEqual(response.status_code, 409)

    def test_history_and_detail(self):
        history = {"mode": "PAPER", "execution": "VALIDATION_ONLY",
                   "total": 1, "limit": 10, "offset": 0,
                   "signals": [self.decision]}
        with patch.object(postgres_signal_store, "list_signals",
                          return_value=history) as listing, \
             patch.object(postgres_signal_store, "get_signal",
                          return_value=self.decision) as detail:
            response = self.client.get(
                "/api/paper/signals?limit=10&offset=0",
                headers=self.headers)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), history)
            listing.assert_called_once_with(
                listing.call_args.args[0], limit=10, offset=0)
            response = self.client.get(
                "/api/paper/signals/sig_api_001", headers=self.headers)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), self.decision)
            detail.assert_called_once()

    def test_missing_signal_returns_404(self):
        with patch.object(postgres_signal_store, "get_signal", return_value=None):
            response = self.client.get("/api/paper/signals/missing",
                                       headers=self.headers)
            self.assertEqual(response.status_code, 404)

    def test_bad_pagination_returns_400(self):
        with patch.object(postgres_signal_store, "list_signals",
                          side_effect=ValueError("Invalid limit")):
            response = self.client.get("/api/paper/signals?limit=0",
                                       headers=self.headers)
            self.assertEqual(response.status_code, 400)

    def test_malformed_payload_returns_422_before_storage(self):
        with patch.object(postgres_signal_store, "record_signal") as write:
            response = self.client.post("/api/paper/signals",
                                        json={"signal_id": "bad"},
                                        headers=self.headers)
            self.assertEqual(response.status_code, 422)
            write.assert_not_called()


if __name__ == "__main__":
    import unittest
    unittest.main()
