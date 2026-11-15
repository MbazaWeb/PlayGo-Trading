"""Opt-in PostgreSQL TEST integration checks for Phase 7C.

All writes are deliberately rolled back. Never run against production.
"""
import os
from pathlib import Path
import unittest
from uuid import uuid4
from datetime import datetime, timezone

from dotenv import load_dotenv
import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg.errors import LockNotAvailable

import postgres_signal_store as store
import postgres_state

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


class _Rollback(Exception):
    pass


@unittest.skipUnless(os.getenv("PLAYGO_RUN_DB_TESTS") == "1",
                     "Requires explicit PostgreSQL TEST opt-in")
class SignalStoreIntegrationTests(unittest.TestCase):
    def test_idempotent_decision_and_conflict_rollback(self):
        dsn = os.getenv("DATABASE_URL", "")
        self.assertTrue(dsn, "DATABASE_URL is required")
        cfg = conninfo_to_dict(dsn)
        self.assertEqual(cfg.get("user"), "postgres.bkxapdsnpucrqptupzbz")
        self.assertEqual(cfg.get("host"), "aws-0-eu-central-1.pooler.supabase.com")
        self.assertEqual(str(cfg.get("port", "5432")), "5432")
        self.assertEqual(cfg.get("dbname"), "postgres")
        signal_id = "phase7c_" + uuid4().hex
        signal = {"signal_id": signal_id, "pair": "EURUSD",
                  "side": "BUY", "confidence": "0.9",
                  "stop_loss": "1.0800",
                  "timestamp": datetime.now(timezone.utc).isoformat()}
        with psycopg.connect(dsn, connect_timeout=8) as conn:
            before = postgres_state.load(conn)
            try:
                with conn.transaction():
                    first = store.record_signal(conn, signal=signal)
                    self.assertEqual(first["execution"], "VALIDATION_ONLY")
                    self.assertEqual(store.record_signal(conn, signal=signal), first)
                    self.assertEqual(store.get_signal(conn, signal_id), first)
                    with self.assertRaises(store.SignalConflict):
                        store.record_signal(conn, signal={**signal, "side": "SELL"})
                    self.assertEqual(store.get_signal(conn, signal_id), first)
                    self.assertEqual(postgres_state.load(conn), before)
                    with conn.cursor() as cur:
                        cur.execute(
                            """select count(*) from playgo_private.documents
                               where collection_name=%s and document_id=%s""",
                            (store.COLLECTION, signal_id))
                        self.assertEqual(cur.fetchone()[0], 1)
                    raise _Rollback()
            except _Rollback:
                pass
            self.assertIsNone(store.get_signal(conn, signal_id))
            self.assertEqual(postgres_state.load(conn), before)


    def test_two_connections_same_signal_are_serialized_without_committing(self):
        """A concurrent writer cannot bypass an uncommitted signal decision.

        The first connection deliberately rolls back, preserving the shared
        TEST database. The second uses a short PostgreSQL lock timeout.
        """
        dsn = os.getenv("DATABASE_URL", "")
        self.assertTrue(dsn, "DATABASE_URL is required")
        cfg = conninfo_to_dict(dsn)
        self.assertEqual(cfg.get("user"), "postgres.bkxapdsnpucrqptupzbz")
        self.assertEqual(cfg.get("host"), "aws-0-eu-central-1.pooler.supabase.com")
        self.assertEqual(str(cfg.get("port", "5432")), "5432")
        self.assertEqual(cfg.get("dbname"), "postgres")
        signal_id = "phase7c_lock_" + uuid4().hex
        signal = {"signal_id": signal_id, "pair": "EURUSD",
                  "side": "BUY", "confidence": "0.9",
                  "stop_loss": "1.0800",
                  "timestamp": datetime.now(timezone.utc).isoformat()}
        with psycopg.connect(dsn, connect_timeout=8) as first, \
             psycopg.connect(dsn, connect_timeout=8) as second:
            baseline = postgres_state.load(first)
            try:
                with first.transaction():
                    recorded = store.record_signal(first, signal=signal)
                    self.assertEqual(recorded["execution"], "VALIDATION_ONLY")
                    with self.assertRaises(LockNotAvailable):
                        with second.transaction():
                            with second.cursor() as cur:
                                cur.execute("set local lock_timeout = '1000ms'")
                            store.record_signal(second, signal=signal)
                    self.assertIsNone(store.get_signal(second, signal_id),
                                      "Uncommitted decision leaked to another connection")
                    self.assertEqual(postgres_state.load(first), baseline)
                    raise _Rollback()
            except _Rollback:
                pass
            self.assertIsNone(store.get_signal(first, signal_id))
            self.assertIsNone(store.get_signal(second, signal_id))
            self.assertEqual(postgres_state.load(first), baseline)


if __name__ == "__main__":
    unittest.main()
