"""Rollback-only PostgreSQL TEST checks for the one-way emergency stop.

WARNING: Engages the stop only inside a transaction deliberately rolled back.
No persistent stop is permitted; never run against production.
"""
import os
from pathlib import Path
import unittest

from dotenv import load_dotenv
import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg.errors import LockNotAvailable

from app import postgres_emergency_stop
from app import postgres_ledger
from app import postgres_state

load_dotenv(Path(__file__).resolve().parents[2] / ".env")


class _Rollback(Exception):
    pass


def configured_test_dsn():
    dsn = os.getenv("DATABASE_URL", "")
    if not dsn:
        raise AssertionError("DATABASE_URL is required")
    cfg = conninfo_to_dict(dsn)
    for key, expected in {
        "user": "postgres.bkxapdsnpucrqptupzbz",
        "host": "aws-0-eu-central-1.pooler.supabase.com",
        "dbname": "postgres",
    }.items():
        if cfg.get(key) != expected:
            raise AssertionError("Refusing non-TEST database: " + key)
    if str(cfg.get("port", "5432")) != "5432":
        raise AssertionError("Refusing unexpected database port")
    return dsn


@unittest.skipUnless(os.getenv("PLAYGO_RUN_DB_TESTS") == "1",
                     "Requires explicit PostgreSQL TEST opt-in")
class EmergencyStopIntegrationTests(unittest.TestCase):
    def test_stop_is_one_way_idempotent_and_rolled_back(self):
        dsn = configured_test_dsn()
        with psycopg.connect(dsn, connect_timeout=8) as conn:
            before = postgres_state.load(conn)
            self.assertFalse(before.get("automation_emergency_stop", False),
                             "Shared TEST stop already engaged; cannot run")
            try:
                with conn.transaction():
                    stopped = postgres_emergency_stop.engage(
                        conn, expected_revision=before["revision"],
                        reason="Rollback-only integration verification")
                    self.assertTrue(stopped["automation_emergency_stop"])
                    self.assertTrue(stopped["paused"])
                    self.assertEqual(stopped["revision"], before["revision"] + 1)
                    self.assertEqual(
                        postgres_emergency_stop.engage(
                            conn, expected_revision=before["revision"],
                            reason="Idempotent retry"), stopped)
                    with self.assertRaises(ValueError):
                        postgres_state.set_paused(
                            conn, expected_revision=stopped["revision"],
                            paused=False)
                    self.assertEqual(postgres_state.load(conn), stopped)
                    raise _Rollback()
            except _Rollback:
                pass
            self.assertEqual(postgres_state.load(conn), before,
                             "Emergency stop escaped rollback")

    def test_second_connection_cannot_override_uncommitted_stop(self):
        dsn = configured_test_dsn()
        with psycopg.connect(dsn, connect_timeout=8) as first, \
             psycopg.connect(dsn, connect_timeout=8) as second:
            before = postgres_state.load(first)
            self.assertFalse(before.get("automation_emergency_stop", False),
                             "Shared TEST stop already engaged; cannot run")
            try:
                with first.transaction():
                    stopped = postgres_emergency_stop.engage(
                        first, expected_revision=before["revision"],
                        reason="Rollback-only concurrent stop check")
                    self.assertTrue(stopped["automation_emergency_stop"])
                    with self.assertRaises(LockNotAvailable):
                        with second.transaction():
                            with second.cursor() as cur:
                                cur.execute("set local lock_timeout = '1000ms'")
                            postgres_emergency_stop.engage(
                                second, expected_revision=before["revision"],
                                reason="Concurrent stop attempt")
                    self.assertEqual(postgres_state.load(first), stopped)
                    raise _Rollback()
            except _Rollback:
                pass
            self.assertEqual(postgres_state.load(first), before)
            self.assertEqual(postgres_state.load(second), before)


if __name__ == "__main__":
    unittest.main()
