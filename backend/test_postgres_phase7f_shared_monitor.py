"""Phase 7F.3 shared monitor cross-process and fail-closed tests."""
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import postgres_operational_monitor as monitor
import postgres_shared_monitor as shared


class SharedMonitorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {
            "PLAYGO_SHARED_MONITOR_PATH": os.path.join(self.tmp.name, "shared.sqlite3")
        })
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_cross_process_atomic_counts(self):
        script = ("import postgres_shared_monitor as m\n"
                  "for _ in range(5): m.failure('DATABASE_ERROR')\n")
        for _ in range(2):
            subprocess.run([sys.executable, "-c", script], check=True,
                           capture_output=True, text=True, timeout=15)
        self.assertEqual(shared.snapshot()["consecutive_failures"], 10)
        shared.success()
        state = shared.snapshot()
        self.assertEqual(state["consecutive_failures"], 0)
        self.assertIsNotNone(state["last_recovery_at"])

    def test_monitor_diagnostics_uses_shared_view(self):
        shared.failure("STATE_ERROR")
        result = monitor.diagnostics()
        self.assertEqual(result["monitor_scope"], "SHARED_SINGLE_HOST")
        self.assertEqual(result["consecutive_failures"], 1)
        self.assertEqual(result["health"], "DEGRADED")
        self.assertIs(result["eligible"], False)
        self.assertEqual(result["execution"], "DISABLED")

    def test_unavailable_shared_monitor_never_reports_healthy(self):
        with patch.object(shared, "snapshot", side_effect=OSError("private path")):
            result = monitor.diagnostics()
        self.assertEqual(result["monitor_scope"], "SHARED_UNAVAILABLE")
        self.assertEqual(result["health"], "DEGRADED")
        self.assertIs(result["automation_enabled"], False)


if __name__ == "__main__":
    unittest.main()
