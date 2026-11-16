"""Phase 7F.4 security and fail-closed regression tests.

No PostgreSQL, Docker, real credentials, or trading execution required.
"""
import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.testclient import TestClient

from app import postgres_api
from app import postgres_incident_spool as spool
from app import postgres_operational_monitor as monitor
from app import postgres_shared_monitor as shared


class Phase7F4SecurityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {
            "PLAYGO_INCIDENT_SPOOL_PATH": os.path.join(self.tmp.name, "incidents.db"),
            "PLAYGO_SHARED_MONITOR_PATH": os.path.join(self.tmp.name, "monitor.db"),
        })
        self.env.start()
        self.client = TestClient(postgres_api.app)
        self.original = monitor.snapshot()
        with monitor._lock:
            monitor._state.update({
                "consecutive_failures": 0, "last_failure_at": None,
                "last_recovery_at": None, "last_failure_category": None,
            })

    def tearDown(self):
        with monitor._lock:
            monitor._state.update(self.original)
        self.env.stop()
        self.tmp.cleanup()

    def test_operational_routes_require_owner(self):
        routes = (
            ("GET", "/api/paper/automation/diagnostics"),
            ("GET", "/api/paper/automation/operational-status"),
            ("GET", "/api/paper/automation/incidents"),
            ("POST", "/api/paper/automation/incidents/flush"),
        )
        with patch.object(postgres_api, "owner", side_effect=HTTPException(401, "Unauthorized")), \
             patch.object(postgres_api, "connect", side_effect=AssertionError("DB must not be reached")):
            for method, path in routes:
                with self.subTest(path=path):
                    response = self.client.request(method, path)
                    self.assertEqual(response.status_code, 401)

    def test_outage_response_fails_closed_and_hides_error(self):
        with patch.object(postgres_api, "owner", return_value="test-owner"), \
             patch.object(postgres_api, "connect",
                          side_effect=RuntimeError("secret-password=DO_NOT_EXPOSE")):
            response = self.client.get("/api/paper/automation/operational-status")
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("DO_NOT_EXPOSE", response.text)
        detail = response.json()["detail"]
        self.assertIs(detail["eligible"], False)
        self.assertIs(detail["automation_enabled"], False)
        self.assertEqual(detail["execution"], "DISABLED")
        self.assertEqual(spool.pending_count(), 1)

    def test_replay_failure_never_leaks_database_error(self):
        spool.enqueue("OUTAGE")
        with patch.object(postgres_api, "owner", return_value="test-owner"), \
             patch.object(postgres_api, "connect",
                          side_effect=RuntimeError("postgresql://secret:password@host")):
            response = self.client.post("/api/paper/automation/incidents/flush")
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("password", response.text)
        self.assertEqual(spool.pending_count(), 1)

    def test_shared_monitor_concurrent_updates(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda _: shared.failure("DATABASE_ERROR"), range(20)))
        self.assertEqual(shared.snapshot()["consecutive_failures"], 20)
        result = monitor.diagnostics()
        self.assertEqual(result["monitor_scope"], "SHARED_SINGLE_HOST")
        self.assertIs(result["eligible"], False)
        self.assertEqual(result["execution"], "DISABLED")

    def test_spool_rejects_credentials_as_categories(self):
        with self.assertRaises(ValueError):
            spool.enqueue("OUTAGE", "postgresql://secret:password@host")
        self.assertEqual(spool.pending_count(), 0)


if __name__ == "__main__":
    unittest.main()
