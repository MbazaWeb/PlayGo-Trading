"""Phase 7F.2 API wiring regression tests without Docker or PostgreSQL."""
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
import postgres_api
import postgres_incident_spool as spool
import postgres_operational_monitor as monitor


class IncidentApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {
            "PLAYGO_INCIDENT_SPOOL_PATH": os.path.join(self.tmp.name, "spool.sqlite3")
        })
        self.env.start()
        self.owner = patch.object(postgres_api, "owner", return_value="test-owner")
        self.owner.start()
        self.client = TestClient(postgres_api.app)
        self.saved = monitor.snapshot()
        with monitor._lock:
            monitor._state.update({
                "consecutive_failures": 0, "last_failure_at": None,
                "last_recovery_at": None, "last_failure_category": None,
            })

    def tearDown(self):
        self.owner.stop()
        self.env.stop()
        with monitor._lock:
            monitor._state.update(self.saved)
        self.tmp.cleanup()

    def test_outage_recorded_once_for_failure_streak(self):
        with patch.object(postgres_api, "connect", side_effect=RuntimeError("db unavailable")):
            for expected in (1, 2):
                result = self.client.get("/api/paper/automation/operational-status")
                self.assertEqual(result.status_code, 503)
                self.assertEqual(result.json()["detail"]["monitor"]["consecutive_failures"], expected)
        self.assertEqual(spool.pending_count(), 1)

    def test_recovery_queues_event(self):
        monitor.record_failure("DATABASE_ERROR")
        with patch.object(postgres_api, "connect", side_effect=RuntimeError("db unavailable")):
            self.client.get("/api/paper/automation/operational-status")
        fake = MagicMock()
        fake.__enter__.return_value = fake
        with patch.object(postgres_api, "connect", return_value=fake), \
             patch.object(postgres_api.postgres_state, "load", return_value={"revision": 1}), \
             patch.object(postgres_api.postgres_accounting, "reconcile", return_value={"consistent": True}), \
             patch.object(postgres_api.postgres_automated_risk.controller, "evaluate",
                          return_value={"reasons": []}):
            result = self.client.get("/api/paper/automation/operational-status")
        self.assertEqual(result.status_code, 200)
        self.assertIs(result.json()["eligible"], False)
        self.assertEqual(spool.pending_count(), 1)
        with spool._open() as local:
            kind = local.execute("SELECT kind FROM incidents").fetchone()[0]
        self.assertEqual(kind, "RECOVERY")

    def test_explicit_flush_requires_configuration(self):
        with patch.dict(os.environ, {}, clear=True):
            response = self.client.post("/api/paper/automation/incidents/flush")
        self.assertEqual(response.status_code, 503)

    def test_flush_is_owner_only(self):
        with patch.object(postgres_api, "owner", side_effect=__import__("fastapi").HTTPException(401)):
            response = self.client.post("/api/paper/automation/incidents/flush")
        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
