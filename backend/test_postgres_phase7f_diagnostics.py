"""Phase 7F.1 diagnostics contract: no database or Docker required."""
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
import postgres_api
import postgres_operational_monitor as monitor


class DiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.original = monitor.snapshot()
        with monitor._lock:
            monitor._state.update({
                "consecutive_failures": 0, "last_failure_at": None,
                "last_recovery_at": None, "last_failure_category": None,
            })
        self.owner_patch = patch.object(postgres_api, "owner", return_value="test-owner")
        self.owner_patch.start()
        self.client = TestClient(postgres_api.app)

    def tearDown(self):
        self.owner_patch.stop()
        with monitor._lock:
            monitor._state.update(self.original)

    def test_initial_read_only_and_disabled(self):
        response = self.client.get("/api/paper/automation/diagnostics")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["monitor_scope"], "PROCESS_LOCAL")
        self.assertEqual(body["health"], "NO_RECORDED_FAILURES")
        self.assertEqual(body["execution"], "DISABLED")
        self.assertIs(body["automation_enabled"], False)
        self.assertIs(body["eligible"], False)
        self.assertNotIn("dsn", body)
        self.assertNotIn("password", body)

    def test_failure_and_recovery(self):
        monitor.record_failure("DATABASE_ERROR")
        monitor.record_failure("STATE_ERROR")
        body = self.client.get("/api/paper/automation/diagnostics").json()
        self.assertEqual(body["health"], "DEGRADED")
        self.assertEqual(body["consecutive_failures"], 2)
        self.assertEqual(body["last_failure_category"], "STATE_ERROR")
        monitor.record_success()
        body = self.client.get("/api/paper/automation/diagnostics").json()
        self.assertEqual(body["consecutive_failures"], 0)
        self.assertIsNotNone(body["last_recovery_at"])
        self.assertIs(body["eligible"], False)

    def test_unrecognized_category_is_sanitized(self):
        monitor.record_failure("password=secret")
        body = self.client.get("/api/paper/automation/diagnostics").json()
        self.assertEqual(body["last_failure_category"], "DATABASE_ERROR")
        self.assertNotIn("secret", str(body))


if __name__ == "__main__":
    unittest.main()
