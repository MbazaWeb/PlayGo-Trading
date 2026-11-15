"""Disposable PostgreSQL integration tests; never target production Supabase.

CI supplies TEST_DATABASE_URL for a local PostgreSQL service. Tests skip when
not explicitly configured. The test database is discarded after each job.
"""
import os
import unittest
from uuid import uuid4
from psycopg.conninfo import conninfo_to_dict

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
        params = conninfo_to_dict(dsn)
        host = params.get("host", "").lower()
        user = params.get("user", "")
        port = str(params.get("port", "5432"))
        local = host in ("localhost", "127.0.0.1", "::1")
        if not local:
            project_ref = "bkxapdsnpucrqptupzbz"
            direct = host == "db." + project_ref + ".supabase.co" and user == "postgres"
            # Supavisor session pooler hostnames vary by region. The
            # project-specific username prevents targeting another project.
            pooler = (
                host.endswith(".pooler.supabase.com")
                and host.count(".") == 3
                and user == "postgres." + project_ref
                and port == "5432"
            )
            if (
                os.getenv("PLAYGO_TEST_PROJECT_REF") != project_ref
                or not (direct or pooler)
            ):
                raise RuntimeError(
                    "Remote tests require the dedicated PlayGo Trading Test "
                    "direct host or session pooler with project-specific username, "
                    "plus PLAYGO_TEST_PROJECT_REF=" + project_ref
                )
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

    def test_realized_pnl_rejects_fabricated_trade_reference(self):
        trade_id = "forged-" + uuid4().hex
        with self.assertRaisesRegex(ValueError, "persisted closed-trade event"):
            postgres_accounting.post(
                self.conn, transaction_id="TRADE:" + trade_id,
                kind="REALIZED_GAIN", amount_cents=100,
                reference="CLOSED:" + trade_id)
        self.conn.rollback()

    def test_realized_pnl_matches_persisted_event(self):
        import json
        trade_id = "ci-trade-" + uuid4().hex
        with self.conn.transaction():
            with self.conn.cursor() as cur:
                cur.execute(
                    "insert into playgo_private.trade_events (event_id, trade_id, event_type, payload) values (%s, %s, %s, %s::jsonb)",
                    ("CLOSED:" + trade_id, trade_id, "PAPER_TRADE_CLOSED",
                     json.dumps({"trade": {"id": trade_id, "pnl": "2.50"}})))
        posted = postgres_accounting.post(
            self.conn, transaction_id="TRADE:" + trade_id,
            kind="REALIZED_GAIN", amount_cents=250,
            reference="CLOSED:" + trade_id)
        self.assertEqual(posted["amount_cents"], 250)

    def test_accounting_reconciliation(self):
        result = postgres_accounting.reconcile(self.conn)
        self.assertTrue(result["consistent"], result["issues"])


if __name__ == "__main__":
    unittest.main()
