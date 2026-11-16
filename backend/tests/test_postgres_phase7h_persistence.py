"""Phase 7H.3 persistence integration using disposable local SQLite only.

Exercises subprocess restarts, pending incident durability, monitor state,
and idempotent local delivery after simulated PostgreSQL commit.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from app import postgres_incident_spool as spool
from app import postgres_shared_monitor as shared


class PersistentMonitoringTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {
            "PLAYGO_INCIDENT_SPOOL_PATH": str(Path(self.tmp.name) / "incidents.sqlite3"),
            "PLAYGO_SHARED_MONITOR_PATH": str(Path(self.tmp.name) / "monitor.sqlite3"),
        })
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def run_child(self, script):
        return subprocess.run([sys.executable, "-c", script], check=True,
                              capture_output=True, text=True, timeout=20,
                              cwd=Path(__file__).resolve().parents[1]).stdout.strip()

    def test_incident_spool_survives_process_restart(self):
        incident = self.run_child(
            "from app import postgres_incident_spool as s; print(s.enqueue('OUTAGE'))")
        self.assertEqual(spool.pending_count(), 1)
        self.assertEqual(self.run_child(
            "from app import postgres_incident_spool as s; print(s.pending_count())"), "1")
        self.assertTrue(incident)

    def test_shared_monitor_survives_restart_and_recovery(self):
        self.run_child(
            "from app import postgres_shared_monitor as m; m.failure('DATABASE_ERROR')")
        self.assertEqual(shared.snapshot()["consecutive_failures"], 1)
        state = json.loads(self.run_child(
            "import json; from app import postgres_shared_monitor as m; print(json.dumps(m.snapshot()))"))
        self.assertEqual(state["consecutive_failures"], 1)
        self.run_child("from app import postgres_shared_monitor as m; m.success()")
        recovered = shared.snapshot()
        self.assertEqual(recovered["consecutive_failures"], 0)
        self.assertIsNotNone(recovered["last_recovery_at"])

    def test_spool_flush_marks_delivered_after_simulated_commit(self):
        incident_id = spool.enqueue("RECOVERY")
        conn = MagicMock()
        cur = conn.cursor.return_value.__enter__.return_value
        self.assertEqual(spool.flush(conn), 1)
        self.assertEqual(spool.pending_count(), 0)
        self.assertEqual(spool.flush(conn), 0)
        self.assertEqual(cur.execute.call_count, 1)
        args = cur.execute.call_args.args[1]
        self.assertEqual(args[1], incident_id)
        self.assertEqual(json.loads(args[2])["execution"], "DISABLED")

    def test_failed_pg_transaction_preserves_pending_for_replay(self):
        spool.enqueue("OUTAGE")
        conn = MagicMock()
        conn.cursor.return_value.__enter__.return_value.execute.side_effect = RuntimeError(
            "simulated PostgreSQL outage")
        with self.assertRaisesRegex(RuntimeError, "simulated PostgreSQL outage"):
            spool.flush(conn)
        self.assertEqual(spool.pending_count(), 1)
        healthy = MagicMock()
        self.assertEqual(spool.flush(healthy), 1)
        self.assertEqual(spool.pending_count(), 0)

    def test_no_sensitive_data_in_persisted_incident(self):
        spool.enqueue("OUTAGE")
        path = Path(os.environ["PLAYGO_INCIDENT_SPOOL_PATH"])
        data = path.read_bytes()
        self.assertNotIn(b"postgresql://", data)
        self.assertNotIn(b"password=", data)
        self.assertEqual(spool.pending_count(), 1)


if __name__ == "__main__":
    unittest.main()
