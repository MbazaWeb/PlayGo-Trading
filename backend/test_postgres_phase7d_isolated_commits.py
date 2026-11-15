"""Destructive Phase 7D tests: dedicated disposable PostgreSQL database ONLY.

Requires PLAYGO_RUN_ISOLATED_DB_TESTS=1 and PLAYGO_ISOLATED_DATABASE_URL
with dbname=playgo_phase7d_isolated. Never reuse DATABASE_URL or any
Supabase shared TEST/production database. Emergency stop is COMMITTED and
cannot be reset. Provision the playgo_private schema and initialized PAPER
state/accounting in this disposable database before running.
"""
from concurrent.futures import ThreadPoolExecutor
import os
from threading import Barrier
import unittest
from uuid import uuid4

import psycopg
from psycopg.conninfo import conninfo_to_dict

import postgres_emergency_stop
import postgres_risk_audit as audit
import postgres_state

ISOLATED_DB_NAME = "playgo_phase7d_isolated"


def isolated_dsn():
    dsn = os.getenv("PLAYGO_ISOLATED_DATABASE_URL", "")
    if not dsn:
        raise AssertionError("PLAYGO_ISOLATED_DATABASE_URL is required")
    cfg = conninfo_to_dict(dsn)
    shared = os.getenv("DATABASE_URL", "")
    if shared and conninfo_to_dict(shared) == cfg:
        raise AssertionError("Isolated database must differ from DATABASE_URL")
    if cfg.get("dbname") != ISOLATED_DB_NAME:
        raise AssertionError("Refusing destructive test: dedicated database name required")
    host = (cfg.get("host") or "").lower()
    if not host or "supabase" in host or "pooler" in host:
        raise AssertionError("Refusing hosted/shared database; use disposable local PostgreSQL")
    if cfg.get("hostaddr"):
        raise AssertionError("hostaddr override is not permitted")
    if host not in ("localhost", "127.0.0.1", "::1"):
        raise AssertionError("Use a local disposable PostgreSQL database only")
    return dsn


def proposal():
    return {"pair": "EURUSD", "side": "BUY", "units": 1000,
            "entry_price": "1.085", "stop_loss": "1.080"}


@unittest.skipUnless(os.getenv("PLAYGO_RUN_ISOLATED_DB_TESTS") == "1",
                     "Requires explicit isolated destructive database opt-in")
class IsolatedCommitTests(unittest.TestCase):
    def setUp(self):
        self.dsn = isolated_dsn()
        with psycopg.connect(self.dsn, connect_timeout=5) as conn:
            with conn.cursor() as cur:
                cur.execute("select to_regclass('playgo_private.documents')")
                self.assertIsNotNone(cur.fetchone()[0], "Provision isolated schema first")
            postgres_state.load(conn)

    def test_a_concurrent_committed_identical_audits(self):
        assessment_id = "phase7d_commit_" + uuid4().hex
        barrier = Barrier(2)

        def worker():
            with psycopg.connect(self.dsn, connect_timeout=5) as conn:
                barrier.wait(timeout=10)
                return audit.record(conn, assessment_id=assessment_id,
                                    proposal=proposal())

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(worker) for _ in range(2)]
            results = [f.result(timeout=35) for f in futures]
        self.assertEqual(results[0], results[1])
        with psycopg.connect(self.dsn, connect_timeout=5) as conn:
            self.assertEqual(audit.get(conn, assessment_id), results[0])
            with conn.cursor() as cur:
                cur.execute(
                    """select count(*) from playgo_private.documents
                       where collection_name=%s and document_id=%s""",
                    (audit.COLLECTION, assessment_id))
                self.assertEqual(cur.fetchone()[0], 1)

    def test_b_concurrent_committed_conflicting_audits(self):
        assessment_id = "phase7d_conflict_" + uuid4().hex
        barrier = Barrier(2)

        def worker(side):
            with psycopg.connect(self.dsn, connect_timeout=5) as conn:
                barrier.wait(timeout=10)
                try:
                    result = audit.record(
                        conn, assessment_id=assessment_id,
                        proposal={**proposal(), "side": side})
                    return ("recorded", result)
                except audit.AuditConflict:
                    return ("conflict", None)

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(worker, side) for side in ("BUY", "SELL")]
            results = [f.result(timeout=35) for f in futures]
        self.assertEqual(sorted(r[0] for r in results),
                         ["conflict", "recorded"])
        with psycopg.connect(self.dsn, connect_timeout=5) as conn:
            stored = audit.get(conn, assessment_id)
            self.assertEqual(stored, next(value for status, value in results
                                          if status == "recorded"))

    def test_z_committed_emergency_stop_survives_reconnect(self):
        with psycopg.connect(self.dsn, connect_timeout=5) as conn:
            before = postgres_state.load(conn)
            if before.get("automation_emergency_stop") is True:
                self.skipTest("Dedicated account already permanently stopped")
            stopped = postgres_emergency_stop.engage(
                conn, expected_revision=before["revision"],
                reason="Destructive isolated durability test")
            self.assertTrue(stopped["automation_emergency_stop"])
            self.assertTrue(stopped["paused"])
        with psycopg.connect(self.dsn, connect_timeout=5) as conn:
            durable = postgres_state.load(conn)
            self.assertTrue(durable["automation_emergency_stop"])
            self.assertEqual(durable["revision"], stopped["revision"])
            with self.assertRaisesRegex(ValueError, "Emergency stop"):
                postgres_state.set_paused(
                    conn, expected_revision=durable["revision"], paused=False)
            self.assertEqual(
                postgres_emergency_stop.engage(
                    conn, expected_revision=before["revision"],
                    reason="Idempotent committed retry"), durable)


if __name__ == "__main__":
    unittest.main()
