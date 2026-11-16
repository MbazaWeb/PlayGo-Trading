"""Phase 7F.2 local spool unit tests; no Docker/PostgreSQL needed."""
import os
import tempfile
import unittest
from unittest.mock import patch

import postgres_incident_spool as spool


class SpoolTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {
            "PLAYGO_INCIDENT_SPOOL_PATH": os.path.join(self.tmp.name, "incidents.sqlite3")
        })
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_enqueue_and_count(self):
        self.assertEqual(spool.pending_count(), 0)
        first = spool.enqueue("OUTAGE")
        second = spool.enqueue("RECOVERY", "STATE_ERROR")
        self.assertNotEqual(first, second)
        self.assertEqual(spool.pending_count(), 2)

    def test_rejects_untrusted_content(self):
        with self.assertRaises(ValueError):
            spool.enqueue("password=secret")
        with self.assertRaises(ValueError):
            spool.enqueue("OUTAGE", "password=secret")
        self.assertEqual(spool.pending_count(), 0)

    def test_bounded_capacity(self):
        with patch.object(spool, "MAX_PENDING", 1):
            spool.enqueue("OUTAGE")
            with self.assertRaises(RuntimeError):
                spool.enqueue("RECOVERY")
        self.assertEqual(spool.pending_count(), 1)

    def test_requires_explicit_path(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RuntimeError):
                spool.enqueue("OUTAGE")

    def test_flush_limit_validation(self):
        with self.assertRaises(ValueError):
            spool.flush(None, limit=0)


if __name__ == "__main__":
    unittest.main()
