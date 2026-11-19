"""Disposable PostgreSQL integration tests; never target production Supabase.

Set PLAYGO_LOCAL_DB_TESTS=1, PLAYGO_LOCAL_DB_PORT, and TEST_DATABASE_URL
for a disposable PostgreSQL database named playgo_test on 127.0.0.1.
"""
import os
import unittest
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from time import time
from unittest.mock import patch
from uuid import uuid4
from psycopg.conninfo import conninfo_to_dict

import psycopg
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from psycopg import sql

from app import postgres_accounting
from app import deriv_signin
from app import postgres_api
from app import postgres_demo_orders
from app import postgres_ledger
from app import postgres_identity
from app import postgres_position_lifecycle
from app import postgres_state
from app.accounting_rules import LedgerConflict


@unittest.skipUnless(os.getenv("PLAYGO_LOCAL_DB_TESTS") == "1", "Disposable local database opt-in required")
class PostgresIntegrationTests(unittest.TestCase):
    def setUp(self):
        port = os.environ.get("PLAYGO_LOCAL_DB_PORT", "")
        dsn = os.environ.get("TEST_DATABASE_URL", "")
        if not dsn.strip():
            self.fail("TEST_DATABASE_URL is required for disposable local database tests")
        params = conninfo_to_dict(dsn)
        expected = {"user": "playgo_test", "host": "127.0.0.1",
                    "dbname": "playgo_test", "port": port}
        if (
            not port.isascii() or not port.isdecimal() or len(port) > 5
            or not 1 <= int(port) <= 65535
            or any(params.get(key) != value for key, value in expected.items())
            or params.keys() - (expected.keys() | {"password", "sslmode"})
        ):
            self.fail("Refusing database target outside the explicit disposable local test settings")
        self.connection_options = {**params, "hostaddr": "127.0.0.1"}
        self.conn = psycopg.connect(**self.connection_options)
        # unittest runs cleanups in reverse order, even when setUp fails.
        self.addCleanup(self.conn.close)
        self.enterContext(self.conn.transaction(force_rollback=True))
        postgres_accounting.initialize(self.conn)
        postgres_state.initialize(self.conn)
        postgres_accounting.post(
            self.conn, transaction_id="OPENING:PAPER:USD:10000",
            kind="CAPITAL_IN", amount_cents=1_000_000,
            reference="SYNTHETIC_ACCOUNT_INITIALIZATION",
        )

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

    def test_accounting_journal_idempotency_and_conflict(self):
        key = "CI:" + uuid4().hex
        args = dict(transaction_id=key, kind="CAPITAL_IN",
                    amount_cents=100, reference="CI_DISPOSABLE")
        with self.conn.transaction(force_rollback=True):
            first = postgres_accounting.post(self.conn, **args)
            second = postgres_accounting.post(self.conn, **args)
            self.assertEqual(first["transaction_id"], second["transaction_id"])
            with self.assertRaises(LedgerConflict):
                postgres_accounting.post(self.conn, **dict(args, amount_cents=200))

    def test_realized_pnl_rejects_fabricated_trade_reference(self):
        trade_id = "forged-" + uuid4().hex
        with self.assertRaisesRegex(ValueError, "persisted closed-trade event"):
            postgres_accounting.post(
                self.conn, transaction_id="TRADE:" + trade_id,
                kind="REALIZED_GAIN", amount_cents=100,
                reference="CLOSED:" + trade_id)

    def test_realized_pnl_matches_persisted_event(self):
        import json
        trade_id = "ci-trade-" + uuid4().hex
        with self.conn.transaction(force_rollback=True):
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

    def test_owner_and_deriv_sessions_are_isolated(self):
        credentials = {"username": "phase_a_owner", "password": uuid4().hex}
        settings = {
            "DERIV_OAUTH_CLIENT_ID": "phase-a-fixture",
            "DERIV_OAUTH_REDIRECT_URI": "https://example.invalid/api/deriv/oauth/callback",
            "DERIV_OAUTH_ENCRYPTION_KEY": Fernet.generate_key().decode(),
        }
        @contextmanager
        def api_connection():
            with self.conn.transaction():
                yield self.conn

        observer = self.conn
        with patch.dict(os.environ, settings), patch.object(postgres_api, "connect", api_connection):
            self.assertEqual(observer.execute("select count(*) from playgo_private.owners").fetchone()[0], 0)
            identity = postgres_identity.bootstrap_owner(observer, **credentials)
            deriv_header = {"Authorization": "Bearer " + deriv_signin.create_session({
                "access_token": "fixture-only", "expires_at": time() + 300,
                "client_id": settings["DERIV_OAUTH_CLIENT_ID"],
            })}
            self.assertEqual(deriv_signin.read_session(deriv_header["Authorization"])["client_id"],
                             settings["DERIV_OAUTH_CLIENT_ID"])
            with TestClient(postgres_api.app) as client:
                login = client.post("/api/identity/login", json=credentials)
                self.assertEqual(login.status_code, 200)
                owner_header = {"Authorization": "Bearer " + login.json()["access_token"]}
                account = client.get("/api/identity/me/paper-account", headers=owner_header)
                self.assertEqual(account.status_code, 200)
                self.assertEqual(account.json()["user_id"], identity["user_id"])
                self.assertFalse(account.json()["personal_account"])
                before = postgres_state.load(observer)
                for headers in ({}, deriv_header):
                    for path in ("/api/state", "/api/ledger/events", "/api/accounting/journals"):
                        with self.subTest(path=path, authenticated=bool(headers)):
                            self.assertEqual(client.get(path, headers=headers).status_code, 401)
                    control = client.post("/api/state/control", headers=headers, json={
                        "expected_revision": before["revision"], "paused": False,
                    })
                    self.assertEqual(control.status_code, 401)
                self.assertEqual(postgres_state.load(observer), before)
                self.assertEqual(client.get("/api/state", headers=owner_header).status_code, 200)
                self.assertEqual(client.post("/api/identity/logout", headers=owner_header).status_code, 200)
                self.assertEqual(client.get("/api/state", headers=owner_header).status_code, 401)

    def test_settlement_rollback_retry_and_append_only_audit(self):
        position_id = "atomic-" + uuid4().hex
        event_id = "CLOSED:" + position_id
        journal_id = "TRADE:" + position_id

        def audit_counts(conn):
            return conn.execute(
                """select
                    (select count(*) from playgo_private.trade_events where event_id=%s),
                    (select count(*) from playgo_private.accounting_journals where transaction_id=%s)""",
                (event_id, journal_id),
            ).fetchone()

        writer = self.conn
        with psycopg.connect(**self.connection_options, autocommit=True) as outside:
            with writer.transaction():
                previous = postgres_state.load(writer)
                prepared = deepcopy(previous)
                prepared.update(
                    paused=False, risk_lock_reason=None, loss_streak=0,
                    day_start_date=datetime.now(timezone.utc).date().isoformat(),
                    day_start_balance=previous["balance"],
                )
                revision = postgres_state.commit(writer, previous, prepared)
                opened = postgres_position_lifecycle.open_position(
                    writer, position_id=position_id, expected_revision=revision,
                    pair="EURUSD", side="BUY", units=1000, stop_loss="1.08000",
                )

            before = postgres_state.load(writer)
            before_accounting = postgres_accounting.reconcile(writer)
            self.assertTrue(before_accounting["consistent"])
            real_post = postgres_accounting.post

            def fail_after_post(conn, **kwargs):
                real_post(conn, **kwargs)
                self.assertEqual(audit_counts(conn), (1, 1))
                self.assertEqual(audit_counts(outside), (0, 0))
                raise RuntimeError("Injected failure after journal write")

            args = dict(position_id=position_id, expected_revision=opened["state_revision"])
            with patch.object(postgres_accounting, "post", side_effect=fail_after_post):
                with self.assertRaisesRegex(RuntimeError, "Injected failure"):
                    postgres_position_lifecycle.close_position(writer, **args)
            self.assertEqual(postgres_state.load(writer), before)
            self.assertEqual(postgres_accounting.reconcile(writer), before_accounting)
            self.assertEqual(audit_counts(writer), (0, 0))

            closed = postgres_position_lifecycle.close_position(writer, **args)
            self.assertEqual(postgres_position_lifecycle.close_position(writer, **args), closed)
            after = postgres_state.load(writer)
            self.assertEqual(after["revision"], before["revision"] + 1)
            self.assertFalse(any(position["id"] == position_id for position in after["positions"]))
            self.assertEqual(audit_counts(writer), (1, 1))
            accounting = postgres_accounting.reconcile(writer)
            self.assertTrue(accounting["consistent"], accounting["issues"])
            self.assertEqual(accounting["balances_cents"]["CASH"], round(after["balance"] * 100))

            role = sql.Identifier("phase_a_dml_" + uuid4().hex)
            with writer.transaction(force_rollback=True):
                writer.execute(sql.SQL("create role {} nologin").format(role))
                writer.execute(sql.SQL("grant usage on schema playgo_private to {}").format(role))
                writer.execute(sql.SQL(
                    "grant select, update, delete, truncate on playgo_private.trade_events, "
                    "playgo_private.accounting_journals to {}"
                ).format(role))
                writer.execute(sql.SQL("set local role {}").format(role))
                for table, column, record in (
                    ("trade_events", "event_id", event_id),
                    ("accounting_journals", "transaction_id", journal_id),
                ):
                    relation = sql.Identifier("playgo_private", table)
                    key = sql.Identifier(column)
                    with self.subTest(table=table, operation="disable triggers"):
                        with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                            with writer.transaction():
                                writer.execute(sql.SQL("alter table {} disable trigger all").format(relation))
                    for statement, values in (
                        (sql.SQL("update {} set {}={} where {}=%s").format(relation, key, key, key), (record,)),
                        (sql.SQL("delete from {} where {}=%s").format(relation, key), (record,)),
                        (sql.SQL("truncate {}").format(relation), ()),
                    ):
                        with self.subTest(table=table, statement=statement.as_string(writer)):
                            with self.assertRaisesRegex(psycopg.errors.InsufficientPrivilege, "append-only"):
                                with writer.transaction():
                                    writer.execute(statement, values)
            self.assertEqual(audit_counts(writer), (1, 1))
            self.assertEqual(audit_counts(outside), (0, 0))


if __name__ == "__main__":
    unittest.main()
