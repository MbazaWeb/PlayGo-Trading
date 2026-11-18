import json
import time
import unittest
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
import psycopg

from app import deriv_demo_bot as bot


class DemoBotTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_account_is_rejected(self):
        response = Mock(status_code=200)
        response.json.return_value = {
            "data": [{"account_id": "real-1", "account_type": "real", "currency": "USD", "balance": 100}]
        }
        client = AsyncMock()
        client.get.return_value = response
        with patch.object(bot.httpx, "AsyncClient") as client_class:
            client_class.return_value.__aenter__.return_value = client
            with self.assertRaises(HTTPException) as error:
                await bot._demo_account("private-token", "real-1")
        self.assertEqual(error.exception.status_code, 403)

    async def test_websocket_url_must_be_scoped_to_demo(self):
        response = Mock(status_code=200)
        response.json.return_value = {
            "data": {"url": "wss://api.derivws.com/trading/v1/options/ws/real?otp=one-time"}
        }
        client = AsyncMock()
        client.post.return_value = response
        with patch.object(bot.httpx, "AsyncClient") as client_class:
            client_class.return_value.__aenter__.return_value = client
            with self.assertRaises(bot.DemoBotProviderError):
                await bot._websocket_url("private-token", "DOT123")

    async def test_trade_uses_stake_limited_call_contract(self):
        class Socket:
            def __init__(self):
                self.sent = []
                self.responses = [
                    json.dumps({"req_id": 1, "proposal": {"id": "p" * 32, "ask_price": 2}}),
                    json.dumps({"req_id": 2, "buy": {"contract_id": 12345}}),
                ]

            async def send(self, value):
                self.sent.append(json.loads(value))

            async def recv(self):
                return self.responses.pop(0)

        socket = Socket()
        with patch.object(bot, "_mark_buy_started") as mark_buy:
            contract_id = await bot._execute_trade(socket, {"currency": "USD"}, "BUY", "DOT123")
        self.assertEqual(contract_id, "12345")
        self.assertEqual(socket.sent[0]["contract_type"], "CALL")
        self.assertEqual(socket.sent[0]["amount"], 2)
        self.assertEqual(socket.sent[0]["duration"], 5)
        self.assertEqual(socket.sent[1], {"buy": "p" * 32, "price": 2.0, "req_id": 2})
        mark_buy.assert_called_once_with("DOT123")

    async def test_trade_rejects_price_above_stake_without_buying(self):
        class Socket:
            def __init__(self):
                self.sent = []

            async def send(self, value):
                self.sent.append(json.loads(value))

            async def recv(self):
                return json.dumps({"req_id": 1, "proposal": {"id": "p" * 32, "ask_price": 2.01}})

        socket = Socket()
        with patch.object(bot, "_mark_buy_started") as mark_buy:
            with self.assertRaises(bot.DemoBotProviderError):
                await bot._execute_trade(socket, {"currency": "USD"}, "SELL", "DOT123")
        self.assertEqual(len(socket.sent), 1)
        self.assertEqual(socket.sent[0]["contract_type"], "PUT")
        mark_buy.assert_not_called()


class DemoBotStateTests(unittest.TestCase):
    def setUp(self):
        self.state = bot._empty_state("DOT123")
        self.state.update({"running": True, "status": "running"})

        @contextmanager
        def lock(_account_id, **_kwargs):
            yield self.state

        self.lock_context = lock
        self.lock_patch = patch.object(bot, "_locked_state", side_effect=lock)
        self.lock_patch.start()
        self.addCleanup(self.lock_patch.stop)

    def test_signal_reservation_is_once_per_candle_and_within_budget(self):
        now = int(time.time())
        day = datetime.fromtimestamp(now, timezone.utc).date().isoformat()
        self.state["day"] = day

        first, reserved = bot._reserve_signal("DOT123", side="BUY", candle_epoch=300, now=now)
        self.assertTrue(reserved)
        self.assertEqual(first["daily_stake"], "2")
        self.assertEqual(first["pending_trade"]["stage"], "proposal")

        repeated, reserved = bot._reserve_signal("DOT123", side="BUY", candle_epoch=300, now=now)
        self.assertFalse(reserved)
        self.assertEqual(repeated["daily_stake"], "2")

        self.state["pending_trade"] = None
        self.state["active_until"] = now + 100
        self.state["last_processed_epoch"] = 300
        active, reserved = bot._reserve_signal("DOT123", side="SELL", candle_epoch=600, now=now)
        self.assertFalse(reserved)
        self.assertEqual(active["status"], "contract_open")
        self.assertEqual(active["daily_stake"], "2")

        self.state["active_until"] = 0
        self.state["daily_stake"] = "4"
        self.state["last_processed_epoch"] = 600
        capped, reserved = bot._reserve_signal("DOT123", side="SELL", candle_epoch=900, now=now)
        self.assertFalse(reserved)
        self.assertFalse(capped["running"])
        self.assertEqual(capped["status"], "daily_budget_reached")

    def test_only_uncertain_buy_keeps_budget_reserved_for_review(self):
        self.state["daily_stake"] = "2"
        self.state["pending_trade"] = {"stage": "proposal"}
        rejected = bot._fail_trade("DOT123", uncertain=False)
        self.assertEqual(rejected["daily_stake"], "0")
        self.assertIsNone(rejected["pending_trade"])

        self.state["daily_stake"] = "2"
        self.state["pending_trade"] = {"stage": "buy"}
        uncertain = bot._fail_trade("DOT123", uncertain=True)
        self.assertEqual(uncertain["daily_stake"], "2")
        self.assertEqual(uncertain["pending_trade"]["stage"], "buy")
        self.assertEqual(uncertain["status"], "needs_review")

    def test_start_rejects_real_account_before_creating_bot_state(self):
        app = FastAPI()
        app.include_router(bot.router)
        client = TestClient(app)
        with patch.object(bot, "_deriv_connection", return_value={"access_token": "private-token"}), \
             patch.object(bot, "_demo_account", new=AsyncMock(side_effect=HTTPException(403, "demo only"))), \
             patch.object(bot, "_locked_state") as state:
            response = client.post(
                 "/api/bot/start",
                json={"account_id": "DOT123"},
                headers={"Authorization": "Bearer deriv_" + "a" * 64},
            )
        self.assertEqual(response.status_code, 403)
        state.assert_not_called()

    def test_start_initializes_the_fixed_demo_configuration(self):
        app = FastAPI()
        app.include_router(bot.router)
        client = TestClient(app)
        self.state["running"] = False
        with patch.object(bot, "_deriv_connection", return_value={"access_token": "private-token", "session_digest": "a" * 64}), \
             patch.object(bot, "_demo_account", new=AsyncMock(return_value={"currency": "USD"})), \
             patch.object(bot, "_locked_state", side_effect=self.lock_context):
            response = client.post(
                "/api/deriv/demo-bot/start",
                json={"account_id": "DOT123"},
                headers={"Authorization": "Bearer deriv_" + "a" * 64},
            )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["running"])
        self.assertEqual(response.json()["execution"], "DEMO_ONLY")
        self.assertEqual(response.json()["stake"], "2")
        self.assertEqual(response.json()["daily_stake_limit"], "5")

    def test_start_reports_missing_run_ledger_schema(self):
        app = FastAPI()
        app.include_router(bot.router)
        client = TestClient(app)
        with patch.object(
            bot,
            "_deriv_connection",
            return_value={"access_token": "private-token", "session_digest": "a" * 64},
        ), patch.object(
            bot, "_demo_account", new=AsyncMock(return_value={"currency": "USD"})
        ), patch.object(
            bot, "_locked_state", side_effect=psycopg.errors.UndefinedTable("missing table")
        ):
            response = client.post(
                "/api/deriv/demo-bot/start",
                json={"account_id": "DOT123"},
                headers={"Authorization": "Bearer deriv_" + "a" * 64},
            )
        self.assertEqual(response.status_code, 503)
        self.assertIn("Apply backend/sql/supabase_foundation.sql", response.json()["detail"])

    def test_start_rejects_an_already_running_bot(self):
        app = FastAPI()
        app.include_router(bot.router)
        client = TestClient(app)
        with patch.object(bot, "_deriv_connection", return_value={"access_token": "private-token", "session_digest": "a" * 64}), \
             patch.object(bot, "_demo_account", new=AsyncMock(return_value={"currency": "USD"})), \
             patch.object(bot, "_locked_state", side_effect=self.lock_context):
            response = client.post(
                "/api/deriv/demo-bot/start",
                json={"account_id": "DOT123"},
                headers={"Authorization": "Bearer deriv_" + "a" * 64},
            )
        self.assertEqual(response.status_code, 409)

    def test_short_stop_route_uses_the_demo_account_guard(self):
        app = FastAPI()
        app.include_router(bot.router)
        client = TestClient(app)
        with patch.object(bot, "_deriv_connection", return_value={"access_token": "private-token"}), \
             patch.object(bot, "_demo_account", new=AsyncMock(side_effect=HTTPException(403, "demo only"))), \
             patch.object(bot, "_locked_state") as state:
            response = client.post(
                "/api/bot/stop",
                json={"account_id": "DOT123"},
                headers={"Authorization": "Bearer deriv_" + "a" * 64},
            )
        self.assertEqual(response.status_code, 403)
        state.assert_not_called()

    def test_start_cannot_bypass_daily_stake_cap(self):
        app = FastAPI()
        app.include_router(bot.router)
        client = TestClient(app)
        self.state["daily_stake"] = "4"
        self.state["running"] = False
        with patch.object(bot, "_deriv_connection", return_value={"access_token": "private-token", "session_digest": "a" * 64}), \
             patch.object(bot, "_demo_account", new=AsyncMock(return_value={"currency": "USD"})), \
             patch.object(bot, "_locked_state", side_effect=self.lock_context):
            response = client.post(
                "/api/deriv/demo-bot/start",
                json={"account_id": "DOT123"},
                headers={"Authorization": "Bearer deriv_" + "a" * 64},
            )
        self.assertEqual(response.status_code, 409)

    def test_resolve_keeps_daily_stake_and_waits_out_uncertain_contract(self):
        app = FastAPI()
        app.include_router(bot.router)
        client = TestClient(app)
        created_at = int(time.time())
        self.state.update({
            "status": "needs_review",
            "running": False,
            "daily_stake": "2",
            "pending_trade": {
                "side": "BUY",
                "candle_epoch": 300,
                "created_at": created_at,
                "stage": "buy",
            },
        })
        with patch.object(bot, "_deriv_connection", return_value={"access_token": "private-token"}), \
             patch.object(bot, "_demo_account", new=AsyncMock(return_value={"currency": "USD"})), \
             patch.object(bot, "_locked_state", side_effect=self.lock_context):
            response = client.post(
                "/api/deriv/demo-bot/resolve",
                json={"account_id": "DOT123", "confirmed_account_review": True},
                headers={"Authorization": "Bearer deriv_" + "a" * 64},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["daily_stake"], "2")
        self.assertEqual(response.json()["status"], "stopped")
        self.assertIsNone(response.json()["pending_trade"])
        self.assertGreaterEqual(response.json()["active_until"], created_at + 360)


class DemoBotLedgerTests(unittest.TestCase):
    def test_new_run_records_demo_configuration_and_session_digest(self):
        class Cursor:
            def execute(self, query, params):
                self.query = query
                self.params = params

            def fetchone(self):
                return ("a3d8e602-621c-4bd0-8ff1-543d9f9e139f",)

        cursor = Cursor()
        state = bot._empty_state("DOT123")
        state["currency"] = "USD"
        session_id = "a" * 64

        bot._sync_run_record(cursor, "DOT123", state, session_id=session_id)

        config = json.loads(cursor.params[2])
        self.assertIn("insert into playgo_private.bot_runs", cursor.query)
        self.assertEqual(cursor.params[:2], (session_id, "DOT123"))
        self.assertEqual(config["strategy"], "EMA_9_21_CROSS")
        self.assertEqual(config["execution"], "DEMO_ONLY")
        self.assertEqual(config["stake"], "2")
        self.assertEqual(state["run_id"], "a3d8e602-621c-4bd0-8ff1-543d9f9e139f")

    def test_run_status_records_uncertain_trade_as_error(self):
        class Cursor:
            def execute(self, query, params):
                self.query = query
                self.params = params

            def fetchone(self):
                return ("a3d8e602-621c-4bd0-8ff1-543d9f9e139f",)

        cursor = Cursor()
        state = bot._empty_state("DOT123")
        state.update({"run_id": "a3d8e602-621c-4bd0-8ff1-543d9f9e139f", "status": "needs_review"})

        bot._sync_run_record(cursor, "DOT123", state)

        self.assertIn("update playgo_private.bot_runs", cursor.query)
        self.assertEqual(cursor.params[0], "error")

    def test_stopped_run_is_recorded_as_stopped(self):
        class Cursor:
            def execute(self, query, params):
                self.query = query
                self.params = params

            def fetchone(self):
                return ("a3d8e602-621c-4bd0-8ff1-543d9f9e139f",)

        cursor = Cursor()
        state = bot._empty_state("DOT123")
        state["run_id"] = "a3d8e602-621c-4bd0-8ff1-543d9f9e139f"

        bot._sync_run_record(cursor, "DOT123", state)

        self.assertEqual(cursor.params[0], "stopped")


if __name__ == "__main__":
    unittest.main()
