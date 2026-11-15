"""Opt-in Phase 6C real PostgreSQL settlement gate.

Runs ONLY with PLAYGO_RUN_DB_TESTS=1 against the allowlisted Supabase TEST
pooler username. All test writes are inside one outer transaction which is
deliberately rolled back, including on successful assertions.

Usage:
    PLAYGO_RUN_DB_TESTS=1 python -m unittest -v test_postgres_position_integration
"""
import os
from pathlib import Path
import unittest
from uuid import uuid4

from dotenv import load_dotenv
from psycopg.conninfo import conninfo_to_dict
import psycopg

import postgres_accounting
import postgres_position_lifecycle as lifecycle
import postgres_state

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

TEST_USER = "postgres.bkxapdsnpucrqptupzbz"
TEST_HOST = "aws-0-eu-central-1.pooler.supabase.com"


class _Rollback(Exception):
    pass


@unittest.skipUnless(os.getenv("PLAYGO_RUN_DB_TESTS") == "1",
                     "Live PostgreSQL test requires explicit opt-in")
class RealPostgresPositionTests(unittest.TestCase):
    def test_atomic_open_close_reconciliation_and_rollback(self):
        dsn = os.getenv("DATABASE_URL", "")
        self.assertTrue(dsn, "DATABASE_URL is required")
        config = conninfo_to_dict(dsn)
        self.assertEqual(config.get("user"), TEST_USER,
                         "Refusing non-TEST database user")
        self.assertEqual(config.get("host"), TEST_HOST,
                         "Refusing non-TEST database host")
        self.assertEqual(str(config.get("port", "5432")), "5432")
        self.assertEqual(config.get("dbname"), "postgres")
        position_id = "it_" + uuid4().hex
        with psycopg.connect(dsn, connect_timeout=8) as conn:
            before = postgres_state.load(conn)
            before_accounting = postgres_accounting.reconcile(conn)
            self.assertTrue(before_accounting["consistent"],
                            "Baseline accounting reconciliation failed")
            self.assertEqual(before["balance"] * 100,
                             before_accounting["balances_cents"]["CASH"],
                             "Paper state balance differs from ledger cash")
            self.assertFalse(before["positions"],
                             "Test requires no existing positions")
            # Roll back every write even after all assertions succeed.
            try:
                with conn.transaction():
                    # No state is left changed after rollback. Force an
                    # unpaused state and today's UTC risk date only inside
                    # this transaction, via the same CAS as production.
                    from copy import deepcopy
                    from datetime import datetime, timezone
                    prepared = deepcopy(before)
                    prepared["paused"] = False
                    prepared["risk_lock_reason"] = None
                    prepared["loss_streak"] = 0
                    prepared["day_start_date"] = datetime.now(timezone.utc).date().isoformat()
                    prepared["day_start_balance"] = before["balance"]
                    rev = postgres_state.commit(conn, before, prepared)
                    opened = lifecycle.open_position(
                        conn, position_id=position_id, expected_revision=rev,
                        pair="EURUSD", side="BUY", units=1000,
                        stop_loss="0.99")
                    self.assertEqual(opened["status"], "OPEN")
                    repeated = lifecycle.open_position(
                        conn, position_id=position_id, expected_revision=rev,
                        pair="EURUSD", side="BUY", units=1000,
                        stop_loss="0.99")
                    self.assertEqual(repeated["position"], opened["position"])
                    with self.assertRaises(lifecycle.PositionConflict):
                        lifecycle.open_position(
                            conn, position_id=position_id, expected_revision=rev,
                            pair="EURUSD", side="SELL", units=1000,
                            stop_loss="1.20")
                    closed = lifecycle.close_position(
                        conn, position_id=position_id,
                        expected_revision=opened["state_revision"])
                    self.assertEqual(closed["status"], "CLOSED")
                    repeated_close = lifecycle.close_position(
                        conn, position_id=position_id, expected_revision=rev)
                    self.assertEqual(repeated_close["position"], closed["position"])
                    accounting = postgres_accounting.reconcile(conn)
                    self.assertTrue(accounting["consistent"], accounting["issues"])
                    current = postgres_state.load(conn)
                    self.assertFalse(current["positions"])
                    self.assertEqual(len(current["trades"]), len(before["trades"]) + 1)
                    self.assertEqual(
                        accounting["balances_cents"]["CASH"],
                        round(current["balance"] * 100))
                    with conn.cursor() as cur:
                        cur.execute(
                            "select count(*) from playgo_private.trade_events where event_id=%s",
                            ("CLOSED:" + position_id,))
                        self.assertEqual(cur.fetchone()[0], 1)
                        cur.execute(
                            "select count(*) from playgo_private.accounting_journals where transaction_id=%s",
                            ("TRADE:" + position_id,))
                        self.assertEqual(cur.fetchone()[0], 1)
                    raise _Rollback()
            except _Rollback:
                pass
            after = postgres_state.load(conn)
            self.assertEqual(after, before, "Rollback did not restore paper state")
            after_accounting = postgres_accounting.reconcile(conn)
            self.assertEqual(after_accounting, before_accounting,
                             "Rollback did not restore accounting")
            with conn.cursor() as cur:
                cur.execute(
                    "select count(*) from playgo_private.trade_events where event_id=%s",
                    ("CLOSED:" + position_id,))
                self.assertEqual(cur.fetchone()[0], 0)
                cur.execute(
                    "select count(*) from playgo_private.accounting_journals where transaction_id=%s",
                    ("TRADE:" + position_id,))
                self.assertEqual(cur.fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
