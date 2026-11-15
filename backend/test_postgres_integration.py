"""Disposable PostgreSQL integration tests; never target production Supabase.

CI supplies TEST_DATABASE_URL for a local PostgreSQL service. Tests skip when
not explicitly configured. The test database is discarded after each job.
"""
import os
import unittest
from uuid import uuid4

import psycopg

import postgres_accounting
import postgres_demo_orders
import postgres_ledger
import postgres_state
from accounting_rules import LedgerConflict


@unittest.skipUnless(os.getenv("TEST_DATABASE_URL"), "Disposable TEST_DATABASE_URL required")
class PostgresIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        dsn = os.environ["TEST_DATABASE_URL"]
        if "localhost" not in dsn and "127.0.0.1" not in dsn:
            raise RuntimeError("Integration tests must use local disposable PostgreSQL")
        cls.conn = psycopg.connect(dsn)
        postgres_accounting.initialize(cls.conn)
        postgres_state.initialize(cls.conn)
        cls.conn.commit()

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def test_paper_state_initialized_once(self):
        first = postgres_state.load(self.conn)
        second = postgres_state.initialize(self.conn)
        self.assertEqual(first["revision"], second["revision"])
        self.assertTrue(first["paused"])

    def test_state_cas_rejects_stale_writer(self):
        first = postgres_state.load(self.conn)
        proposed = dict(first, ticks=first["ticks"] + 1)
        new_revision = postgres_state.commit(self.conn, first, proposed)
        self.assertEqual(new_revision, first["revision"] + 1)
        with self.assertRaises(postgres_ledger.StaleStateError):
            postgres_state.commit(self.conn, first, proposed)
        self.conn.rollback()

    def test_demo_order_replay_and_conflict(self):
        key = "ci-" + uuid4().hex
        args = dict(client_order_id=key, pair="EURUSD", side="BUY",
                    units=100, bid="1.0800", ask="1.0802")
        first = postgres_demo_orders.submit_demo_order(self.conn, **args)
        second = postgres_demo_orders.submit_demo_order(self.conn, **args)
        self.assertEqual(first["fill"], second["fill"])
        self.assertEqual(first["status"], "FILLED")
        with self.assertRaises(postgres_demo_orders.OrderConflict):
            postgres_demo_orders.submit_demo_order(
                self.conn, **dict(args, units=200))
        self.conn.rollback()

    def test_accounting_journal_idempotency_and_conflict(self):
        key = "CI:" + uuid4().hex
        args = dict(transaction_id=key, kind="CAPITAL_IN",
                    amount_cents=100, reference="CI_DISPOSABLE")
        first = postgres_accounting.post(self.conn, **args)
        second = postgres_accounting.post(self.conn, **args)
        self.assertEqual(first["transaction_id"], second["transaction_id"])
        with self.assertRaises(LedgerConflict):
            postgres_accounting.post(self.conn, **dict(args, amount_cents=200))
        self.conn.rollback()

    def test_accounting_reconciliation(self):
        result = postgres_accounting.reconcile(self.conn)
        self.assertTrue(result["consistent"], result["issues"])


if __name__ == "__main__":
    unittest.main()
