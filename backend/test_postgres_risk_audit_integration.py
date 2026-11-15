"""Opt-in PostgreSQL TEST integration checks for Phase 7D risk auditing.

All audit inserts are inside explicit rollback-only transactions. No writes
are committed. Never point these tests at production or shared live accounts.
"""
import os
from pathlib import Path
import unittest
from uuid import uuid4

from dotenv import load_dotenv
import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg.errors import LockNotAvailable

import postgres_accounting
import postgres_risk_audit as audit
import postgres_state

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


class _Rollback(Exception):
    pass


def test_dsn():
    dsn = os.getenv("DATABASE_URL", "")
    if not dsn:
        raise AssertionError("DATABASE_URL is required")
    cfg = conninfo_to_dict(dsn)
    expected = {
        "user": "postgres.bkxapdsnpucrqptupzbz",
        "host": "aws-0-eu-central-1.pooler.supabase.com",
        "dbname": "postgres",
    }
    for key, value in expected.items():
        if cfg.get(key) != value:
            raise AssertionError("Refusing non-TEST database: " + key)
    if str(cfg.get("port", "5432")) != "5432":
        raise AssertionError("Refusing unexpected database port")
    return dsn


def proposal():
    return {"pair": "EURUSD", "side": "BUY", "units": 1000,
            "entry_price": "1.085", "stop_loss": "1.080"}


def audit_count(conn, assessment_id):
    with conn.cursor() as cur:
        cur.execute(
            """select count(*) from playgo_private.documents
               where collection_name=%s and document_id=%s""",
            (audit.COLLECTION, assessment_id))
        return cur.fetchone()[0]


@unittest.skipUnless(os.getenv("PLAYGO_RUN_DB_TESTS") == "1",
                     "Requires explicit PostgreSQL TEST opt-in")
class RiskAuditIntegrationTests(unittest.TestCase):
    def test_idempotency_conflict_and_rollback(self):
        dsn = test_dsn()
        assessment_id = "phase7d_" + uuid4().hex
        with psycopg.connect(dsn, connect_timeout=8) as conn:
            before = postgres_state.load(conn)
            before_accounting = postgres_accounting.reconcile(conn)
            self.assertTrue(before_accounting["consistent"],
                            "Refusing to assess inconsistent TEST accounting")
            try:
                with conn.transaction():
                    first = audit.record(
                        conn, assessment_id=assessment_id, proposal=proposal())
                    self.assertEqual(first["execution"], "OBSERVATION_ONLY")
                    self.assertEqual(first["state_revision"], before["revision"])
                    self.assertEqual(first["decision"]["mode"], "PAPER")
                    self.assertEqual(first["decision"]["execution"], "OBSERVATION_ONLY")
                    self.assertIn("AUTOMATION_DISABLED",
                                  first["decision"]["reasons"])
                    self.assertEqual(
                        audit.record(conn, assessment_id=assessment_id,
                                     proposal=proposal()), first)
                    self.assertEqual(audit.get(conn, assessment_id), first)
                    self.assertEqual(audit_count(conn, assessment_id), 1)
                    with self.assertRaises(audit.AuditConflict):
                        audit.record(conn, assessment_id=assessment_id,
                                     proposal={**proposal(), "side": "SELL"})
                    self.assertEqual(audit.get(conn, assessment_id), first)
                    self.assertEqual(postgres_state.load(conn), before)
                    self.assertEqual(postgres_accounting.reconcile(conn),
                                     before_accounting)
                    raise _Rollback()
            except _Rollback:
                pass
            self.assertIsNone(audit.get(conn, assessment_id))
            self.assertEqual(audit_count(conn, assessment_id), 0)
            self.assertEqual(postgres_state.load(conn), before)
            self.assertEqual(postgres_accounting.reconcile(conn),
                             before_accounting)

    def test_concurrent_uncommitted_assessment_is_not_visible(self):
        dsn = test_dsn()
        assessment_id = "phase7d_lock_" + uuid4().hex
        with psycopg.connect(dsn, connect_timeout=8) as first, \
             psycopg.connect(dsn, connect_timeout=8) as second:
            before = postgres_state.load(first)
            try:
                with first.transaction():
                    result = audit.record(
                        first, assessment_id=assessment_id, proposal=proposal())
                    self.assertEqual(result["execution"], "OBSERVATION_ONLY")
                    self.assertIsNone(audit.get(second, assessment_id),
                                      "Uncommitted audit leaked")
                    with self.assertRaises(LockNotAvailable):
                        with second.transaction():
                            with second.cursor() as cur:
                                cur.execute("set local lock_timeout = '1000ms'")
                            audit.record(
                                second, assessment_id=assessment_id,
                                proposal=proposal())
                    self.assertIsNone(audit.get(second, assessment_id))
                    self.assertEqual(postgres_state.load(first), before)
                    raise _Rollback()
            except _Rollback:
                pass
            self.assertIsNone(audit.get(first, assessment_id))
            self.assertIsNone(audit.get(second, assessment_id))
            self.assertEqual(postgres_state.load(first), before)


if __name__ == "__main__":
    unittest.main()
