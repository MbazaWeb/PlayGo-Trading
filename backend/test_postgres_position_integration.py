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
from unittest.mock import patch

from dotenv import load_dotenv
from psycopg.conninfo import conninfo_to_dict
import psycopg
from psycopg.errors import LockNotAvailable

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
            self.assertEqual(before_accounting["balances_cents"]["CASH"],
                             round(before["balance"] * 100),
                             "Baseline PAPER cash and ledger cash must agree")
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
                    from decimal import Decimal
                    entry = Decimal(str(prepared["quotes"]["EURUSD"]["ask"]))
                    stop = str(entry - Decimal("0.005"))
                    opened = lifecycle.open_position(
                        conn, position_id=position_id, expected_revision=rev,
                        pair="EURUSD", side="BUY", units=1000,
                        stop_loss=stop)
                    self.assertEqual(opened["status"], "OPEN")
                    repeated = lifecycle.open_position(
                        conn, position_id=position_id, expected_revision=rev,
                        pair="EURUSD", side="BUY", units=1000,
                        stop_loss=stop)
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
                    self.assertEqual(repeated_close["state_revision"], closed["state_revision"])
                    # A retry with an obsolete revision must not post a
                    # second settlement or advance state revision.
                    retry_with_stale_revision = lifecycle.close_position(
                        conn, position_id=position_id, expected_revision=0)
                    self.assertEqual(retry_with_stale_revision, closed)
                    self.assertEqual(postgres_state.load(conn)["revision"],
                                     closed["state_revision"])
                    accounting = postgres_accounting.reconcile(conn)
                    self.assertTrue(accounting["consistent"], accounting["issues"])
                    current = postgres_state.load(conn)
                    self.assertFalse(current["positions"])
                    self.assertEqual(len(current["trades"]), len(before["trades"]) + 1)
                    self.assertEqual(
                        accounting["balances_cents"]["CASH"] - round(current["balance"] * 100),
                        0,
                        "PAPER cash and ledger cash diverged during settlement")
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

    def test_accounting_failure_rolls_back_closed_trade_and_event(self):
        """A failed journal must never persist a CLOSED position or trade event."""
        dsn = os.getenv("DATABASE_URL", "")
        self.assertTrue(dsn, "DATABASE_URL is required")
        config = conninfo_to_dict(dsn)
        self.assertEqual(config.get("user"), TEST_USER)
        self.assertEqual(config.get("host"), TEST_HOST)
        self.assertEqual(str(config.get("port", "5432")), "5432")
        self.assertEqual(config.get("dbname"), "postgres")
        position_id = "fi_" + uuid4().hex
        with psycopg.connect(dsn, connect_timeout=8) as conn:
            before = postgres_state.load(conn)
            before_accounting = postgres_accounting.reconcile(conn)
            self.assertTrue(before_accounting["consistent"])
            self.assertEqual(before_accounting["balances_cents"]["CASH"],
                             round(before["balance"] * 100))
            self.assertFalse(before["positions"], "Test requires no open positions")
            try:
                with conn.transaction():
                    from copy import deepcopy
                    from datetime import datetime, timezone
                    from decimal import Decimal
                    prepared = deepcopy(before)
                    prepared["paused"] = False
                    prepared["risk_lock_reason"] = None
                    prepared["loss_streak"] = 0
                    prepared["day_start_date"] = datetime.now(timezone.utc).date().isoformat()
                    prepared["day_start_balance"] = before["balance"]
                    revision = postgres_state.commit(conn, before, prepared)
                    entry = Decimal(str(prepared["quotes"]["EURUSD"]["ask"]))
                    opened = lifecycle.open_position(
                        conn, position_id=position_id, expected_revision=revision,
                        pair="EURUSD", side="BUY", units=1000,
                        stop_loss=str(entry - Decimal("0.005")))
                    opened_state = postgres_state.load(conn)
                    with patch.object(lifecycle.postgres_accounting, "post",
                                      side_effect=RuntimeError("INJECTED_JOURNAL_FAILURE")):
                        with self.assertRaisesRegex(RuntimeError, "INJECTED_JOURNAL_FAILURE"):
                            lifecycle.close_position(
                                conn, position_id=position_id,
                                expected_revision=opened["state_revision"])
                    self.assertEqual(postgres_state.load(conn), opened_state,
                                     "Failed settlement modified persisted state")
                    with conn.cursor() as cur:
                        cur.execute("select count(*) from playgo_private.trade_events where event_id=%s",
                                    ("CLOSED:" + position_id,))
                        self.assertEqual(cur.fetchone()[0], 0)
                        cur.execute("select count(*) from playgo_private.accounting_journals where transaction_id=%s",
                                    ("TRADE:" + position_id,))
                        self.assertEqual(cur.fetchone()[0], 0)
                    self.assertEqual(postgres_accounting.reconcile(conn), before_accounting)
                    raise _Rollback()
            except _Rollback:
                pass
            self.assertEqual(postgres_state.load(conn), before)
            self.assertEqual(postgres_accounting.reconcile(conn), before_accounting)
            with conn.cursor() as cur:
                cur.execute("select count(*) from playgo_private.trade_events where event_id=%s",
                            ("CLOSED:" + position_id,))
                self.assertEqual(cur.fetchone()[0], 0)

    def test_concurrent_state_row_lock_exclusion(self):
        """Two connections cannot simultaneously acquire the PAPER state write lock.

        Read-only contention test: no position or accounting rows are changed.
        This checks PostgreSQL's row-lock primitive, not a full concurrent
        open/close settlement race.
        """
        dsn = os.getenv("DATABASE_URL", "")
        self.assertTrue(dsn, "DATABASE_URL is required")
        config = conninfo_to_dict(dsn)
        self.assertEqual(config.get("user"), TEST_USER)
        self.assertEqual(config.get("host"), TEST_HOST)
        self.assertEqual(str(config.get("port", "5432")), "5432")
        self.assertEqual(config.get("dbname"), "postgres")
        sql = ("select revision from playgo_private.documents "
               "where collection_name='app_state' and document_id='paper-trading-state' "
               "for update")
        with psycopg.connect(dsn, connect_timeout=8) as first:
            with psycopg.connect(dsn, connect_timeout=8) as second:
                before = postgres_state.load(first)
                before_accounting = postgres_accounting.reconcile(first)
                # Finish implicit read transactions before locking the row.
                first.rollback()
                second.rollback()
                with first.transaction():
                    with first.cursor() as cur:
                        cur.execute(sql)
                        self.assertEqual(cur.fetchone()[0], before["revision"])
                    with self.assertRaises(LockNotAvailable):
                        with second.transaction():
                            with second.cursor() as cur:
                                cur.execute("set local lock_timeout = '1000ms'")
                                cur.execute(sql)
                    # The blocked writer must not modify any state.
                    self.assertEqual(postgres_state.load(first), before)
                self.assertEqual(postgres_state.load(second), before)
                self.assertEqual(postgres_accounting.reconcile(second),
                                 before_accounting)

    def test_concurrent_open_request_cannot_bypass_state_lock(self):
        """An open request from a second connection times out while state is locked."""
        dsn = os.getenv("DATABASE_URL", "")
        self.assertTrue(dsn)
        config = conninfo_to_dict(dsn)
        self.assertEqual(config.get("user"), TEST_USER)
        self.assertEqual(config.get("host"), TEST_HOST)
        self.assertEqual(str(config.get("port", "5432")), "5432")
        self.assertEqual(config.get("dbname"), "postgres")
        with psycopg.connect(dsn, connect_timeout=8) as first:
            with psycopg.connect(dsn, connect_timeout=8) as second:
                before = postgres_state.load(first)
                baseline = postgres_accounting.reconcile(first)
                self.assertTrue(baseline["consistent"])
                self.assertEqual(baseline["balances_cents"]["CASH"],
                                 round(before["balance"] * 100))
                first.rollback()
                second.rollback()
                from decimal import Decimal
                entry = Decimal(str(before["quotes"]["EURUSD"]["ask"]))
                stop = str(entry - Decimal("0.005"))
                with first.transaction():
                    with first.cursor() as cur:
                        cur.execute(
                            "select revision from playgo_private.documents "
                            "where collection_name='app_state' "
                            "and document_id='paper-trading-state' for update")
                        self.assertEqual(cur.fetchone()[0], before["revision"])
                    with self.assertRaises(LockNotAvailable):
                        with second.transaction():
                            with second.cursor() as cur:
                                cur.execute("set local lock_timeout = '1000ms'")
                            lifecycle.open_position(
                                second, position_id="race_" + uuid4().hex,
                                expected_revision=before["revision"],
                                pair="EURUSD", side="BUY", units=1000,
                                stop_loss=stop)
                self.assertEqual(postgres_state.load(second), before)
                self.assertEqual(postgres_accounting.reconcile(second), baseline)

    def test_open_rejects_cash_discrepancy_before_mutation(self):
        """Reject opening if the accounting journal and PAPER cash diverge."""
        dsn = os.getenv("DATABASE_URL", "")
        self.assertTrue(dsn)
        config = conninfo_to_dict(dsn)
        self.assertEqual(config.get("user"), TEST_USER)
        self.assertEqual(config.get("host"), TEST_HOST)
        self.assertEqual(str(config.get("port", "5432")), "5432")
        self.assertEqual(config.get("dbname"), "postgres")
        with psycopg.connect(dsn, connect_timeout=8) as conn:
            before = postgres_state.load(conn)
            baseline = postgres_accounting.reconcile(conn)
            self.assertTrue(baseline["consistent"])
            self.assertEqual(baseline["balances_cents"]["CASH"],
                             round(before["balance"] * 100))
            from copy import deepcopy
            from datetime import datetime, timezone
            from decimal import Decimal
            try:
                with conn.transaction():
                    prepared = deepcopy(before)
                    prepared["paused"] = False
                    prepared["risk_lock_reason"] = None
                    prepared["loss_streak"] = 0
                    prepared["day_start_date"] = datetime.now(timezone.utc).date().isoformat()
                    prepared["day_start_balance"] = before["balance"]
                    revision = postgres_state.commit(conn, before, prepared)
                    altered = dict(baseline)
                    altered["balances_cents"] = dict(baseline["balances_cents"])
                    altered["balances_cents"]["CASH"] += 100
                    entry = Decimal(str(prepared["quotes"]["EURUSD"]["ask"]))
                    with patch.object(lifecycle.postgres_accounting, "reconcile",
                                      return_value=altered):
                        with self.assertRaisesRegex(
                            lifecycle.pricing.RiskRejected,
                            "accounting reconciliation failed"
                        ):
                            lifecycle.open_position(
                                conn, position_id="mis_" + uuid4().hex,
                                expected_revision=revision,
                                pair="EURUSD", side="BUY", units=1000,
                                stop_loss=str(entry - Decimal("0.005")))
                    self.assertEqual(postgres_state.load(conn)["revision"], revision)
                    raise _Rollback()
            except _Rollback:
                pass
            self.assertEqual(postgres_state.load(conn), before)
            self.assertEqual(postgres_accounting.reconcile(conn), baseline)

    def test_concurrent_close_is_blocked_during_atomic_settlement(self):
        """Competing close cannot settle while another transaction owns the row.

        The first close is deliberately rolled back; no TEST data persists.
        A subsequent committed-retry race remains a separate validation gate.
        """
        dsn = os.getenv("DATABASE_URL", "")
        self.assertTrue(dsn)
        config = conninfo_to_dict(dsn)
        self.assertEqual(config.get("user"), TEST_USER)
        self.assertEqual(config.get("host"), TEST_HOST)
        self.assertEqual(str(config.get("port", "5432")), "5432")
        self.assertEqual(config.get("dbname"), "postgres")
        position_id = "cc_" + uuid4().hex
        from copy import deepcopy
        from datetime import datetime, timezone
        from decimal import Decimal
        with psycopg.connect(dsn, connect_timeout=8) as first:
            with psycopg.connect(dsn, connect_timeout=8) as second:
                before = postgres_state.load(first)
                baseline = postgres_accounting.reconcile(first)
                self.assertTrue(baseline["consistent"])
                self.assertEqual(baseline["balances_cents"]["CASH"],
                                 round(before["balance"] * 100))
                self.assertFalse(before["positions"])
                first.rollback()
                second.rollback()
                try:
                    with first.transaction():
                        prepared = deepcopy(before)
                        prepared["paused"] = False
                        prepared["risk_lock_reason"] = None
                        prepared["loss_streak"] = 0
                        prepared["day_start_date"] = datetime.now(timezone.utc).date().isoformat()
                        prepared["day_start_balance"] = before["balance"]
                        revision = postgres_state.commit(first, before, prepared)
                        entry = Decimal(str(prepared["quotes"]["EURUSD"]["ask"]))
                        opened = lifecycle.open_position(
                            first, position_id=position_id,
                            expected_revision=revision,
                            pair="EURUSD", side="BUY", units=1000,
                            stop_loss=str(entry - Decimal("0.005")))
                        closed = lifecycle.close_position(
                            first, position_id=position_id,
                            expected_revision=opened["state_revision"])
                        self.assertEqual(closed["status"], "CLOSED")
                        with self.assertRaises(LockNotAvailable):
                            with second.transaction():
                                with second.cursor() as cur:
                                    cur.execute("set local lock_timeout = '1000ms'")
                                lifecycle.close_position(
                                    second, position_id=position_id,
                                    expected_revision=opened["state_revision"])
                        # One and only one settlement is visible to the
                        # first transaction; the second wrote nothing.
                        with first.cursor() as cur:
                            cur.execute(
                                "select count(*) from playgo_private.trade_events "
                                "where event_id=%s", ("CLOSED:" + position_id,))
                            self.assertEqual(cur.fetchone()[0], 1)
                            cur.execute(
                                "select count(*) from playgo_private.accounting_journals "
                                "where transaction_id=%s", ("TRADE:" + position_id,))
                            self.assertEqual(cur.fetchone()[0], 1)
                        accounting = postgres_accounting.reconcile(first)
                        state = postgres_state.load(first)
                        self.assertTrue(accounting["consistent"])
                        self.assertEqual(accounting["balances_cents"]["CASH"],
                                         round(state["balance"] * 100))
                        raise _Rollback()
                except _Rollback:
                    pass
                self.assertEqual(postgres_state.load(first), before)
                self.assertEqual(postgres_accounting.reconcile(first), baseline)
                with second.cursor() as cur:
                    cur.execute(
                        "select count(*) from playgo_private.trade_events "
                        "where event_id=%s", ("CLOSED:" + position_id,))
                    self.assertEqual(cur.fetchone()[0], 0)
                    cur.execute(
                        "select count(*) from playgo_private.accounting_journals "
                        "where transaction_id=%s", ("TRADE:" + position_id,))
                    self.assertEqual(cur.fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
