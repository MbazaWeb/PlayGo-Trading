"""Isolated HTTP route contract tests; no database or broker access."""
import os
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from app import postgres_api
from app import postgres_ledger


class PostgresApiContractTests(unittest.TestCase):
    def test_database_url_without_password_is_rejected_before_connecting(self):
        dsn = "postgresql://playgo_test@127.0.0.1:5432/playgo_disposable"
        with patch.dict(os.environ, {"DATABASE_URL": dsn}), patch.object(
            postgres_api.psycopg, "connect"
        ) as connect:
            with self.assertRaisesRegex(RuntimeError, "explicit database user and password"):
                postgres_api.connect()
        connect.assert_not_called()

    def test_public_registration_is_disabled(self):
        with self.assertRaises(HTTPException) as caught:
            postgres_api.register_disabled()
        self.assertEqual(caught.exception.status_code, 403)

    def test_state_requires_owner_authentication(self):
        with patch.object(postgres_api, "owner", side_effect=HTTPException(401, "Unauthorized")):
            with self.assertRaises(HTTPException) as caught:
                postgres_api.paper_state(authorization="")
        self.assertEqual(caught.exception.status_code, 401)

    def test_state_control_rejects_stale_revision(self):
        payload = postgres_api.PaperControlRequest(expected_revision=0, paused=False)
        with patch.object(postgres_api, "owner", return_value="test-owner"), patch.object(
            postgres_api, "connect"
        ) as connect, patch.object(
            postgres_api.postgres_state, "set_paused",
            side_effect=postgres_ledger.StaleStateError("stale"),
        ):
            with self.assertRaises(HTTPException) as caught:
                postgres_api.paper_control(payload, authorization="Bearer test")
        self.assertEqual(caught.exception.status_code, 409)
        connect.assert_called_once()

    def test_cycle_is_observation_only(self):
        payload = postgres_api.PaperCycleRequest(expected_revision=2)
        with patch.object(postgres_api, "owner", return_value="test-owner"), patch.object(
            postgres_api, "connect"
        ), patch.object(
            postgres_api.postgres_cycle, "run_cycle",
            return_value={"revision": 3, "paused": False},
        ):
            result = postgres_api.synthetic_cycle(payload, authorization="Bearer test")
        self.assertEqual(result["execution"], "OBSERVATION_ONLY")
        self.assertEqual(result["state"]["revision"], 3)

    def test_invalid_order_limit_rejected_before_db(self):
        with patch.object(postgres_api, "owner", return_value="test-owner"):
            with self.assertRaises(HTTPException) as caught:
                postgres_api.pending_demo_orders(limit=201, authorization="Bearer test")
        self.assertEqual(caught.exception.status_code, 400)


class ResearchApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_backtest_is_read_only_and_returns_research_mode(self):
        candles = []
        for index in range(5):
            candles.append({
                "epoch": 1_800_000_000 + index * 300,
                "open": "1.10000",
                "high": "1.10010",
                "low": "1.09990",
                "close": "1.10000",
            })
        candles.extend([
            {
                "epoch": 1_800_001_500,
                "open": "1.10000",
                "high": "1.10050",
                "low": "1.09990",
                "close": "1.10030",
            },
            {
                "epoch": 1_800_001_800,
                "open": "1.10030",
                "high": "1.10080",
                "low": "1.10020",
                "close": "1.10070",
            },
        ])
        with patch.object(postgres_api, "owner"), patch.object(
            postgres_api.deriv_market_data,
            "fetch_public_candles",
            new=AsyncMock(return_value={"candles": candles}),
        ) as fetch, patch.object(postgres_api, "connect") as connect:
            result = await postgres_api.research_breakout(
                pair="EURUSD",
                granularity=300,
                count=100,
                lookback=5,
                authorization="Bearer test",
            )

        self.assertEqual(result["execution"], "RESEARCH_ONLY")
        self.assertEqual(result["data_source"], "DERIV_PUBLIC_CANDLES")
        fetch.assert_awaited_once_with(
            "frxEURUSD", count=100, granularity=300)
        connect.assert_not_called()

    async def test_backtest_rejects_unsupported_pair_before_fetch(self):
        with patch.object(postgres_api, "owner"), patch.object(
            postgres_api.deriv_market_data,
            "fetch_public_candles",
            new=AsyncMock(),
        ) as fetch:
            with self.assertRaises(HTTPException) as caught:
                await postgres_api.research_breakout(
                    pair="USDJPY", authorization="Bearer test")

        self.assertEqual(caught.exception.status_code, 400)
        fetch.assert_not_awaited()

    async def test_backtest_rejects_invalid_candle_interval_before_fetch(self):
        with patch.object(postgres_api, "owner"), patch.object(
            postgres_api.deriv_market_data,
            "fetch_public_candles",
            new=AsyncMock(),
        ) as fetch:
            with self.assertRaises(HTTPException) as caught:
                await postgres_api.research_breakout(
                    pair="EURUSD", granularity=61,
                    authorization="Bearer test")

        self.assertEqual(caught.exception.status_code, 400)
        fetch.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
