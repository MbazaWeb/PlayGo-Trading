"""Offline safety checks for the Deriv public tick adapter."""
import json
import unittest
from unittest.mock import AsyncMock, patch
from app.deriv_market_data import (
    PUBLIC_WS_URL,
    DerivMarketDataError,
    active_symbols_request,
    candles_request,
    fetch_public_forex_markets,
    fetch_public_candles,
    parse_candles,
    parse_active_forex_symbols,
    parse_tick,
    tick_request,
    fetch_public_tick,
    fetch_public_forex_markets,
)


class DerivMarketDataTests(unittest.IsolatedAsyncioTestCase):
    def test_request_has_no_auth_or_trade_operation(self):
        self.assertEqual(tick_request("frxEURUSD"), {"ticks": "frxEURUSD", "subscribe": 0})

    def test_symbol_allowlist(self):
        with self.assertRaises(DerivMarketDataError):
            tick_request("R_100")
        self.assertEqual(tick_request("frxAUDHUF"), {"ticks": "frxAUDHUF", "subscribe": 0})

    def test_active_forex_catalog_filters_and_sorts(self):
        catalog = parse_active_forex_symbols({
            "msg_type": "active_symbols",
            "active_symbols": [
                {
                    "market": "forex",
                    "underlying_symbol": "frxUSDJPY",
                    "underlying_symbol_name": "USD/JPY",
                    "pip_size": 0.001,
                    "exchange_is_open": 1,
                    "is_trading_suspended": 0,
                },
                {
                    "market": "synthetic_index",
                    "underlying_symbol": "R_100",
                    "underlying_symbol_name": "Volatility 100",
                    "pip_size": 0.01,
                    "exchange_is_open": 1,
                    "is_trading_suspended": 0,
                },
                {
                    "market": "forex",
                    "underlying_symbol": "frxAUDHUF",
                    "underlying_symbol_name": "AUD/HUF",
                    "pip_size": 0.0001,
                    "exchange_is_open": 0,
                    "is_trading_suspended": 1,
                },
            ],
        })
        self.assertEqual(active_symbols_request(), {"active_symbols": "brief"})
        self.assertEqual([market["pair"] for market in catalog["markets"]], ["AUDHUF", "USDJPY"])
        self.assertFalse(catalog["markets"][0]["exchange_is_open"])
        self.assertTrue(catalog["markets"][0]["is_trading_suspended"])
        self.assertEqual(catalog["execution"], "DISABLED")

    def test_active_forex_catalog_rejects_malformed_forex_rows(self):
        with self.assertRaises(DerivMarketDataError):
            parse_active_forex_symbols({
                "msg_type": "active_symbols",
                "active_symbols": [{
                    "market": "forex",
                    "underlying_symbol": "R_100",
                    "underlying_symbol_name": "Invalid",
                    "pip_size": 0.01,
                    "exchange_is_open": 1,
                    "is_trading_suspended": 0,
                }],
            })

    def test_valid_tick(self):
        result = parse_tick(
            {"msg_type": "tick", "tick": {"symbol": "frxEURUSD", "quote": 1.0852, "epoch": 1790000000}},
            "frxEURUSD",
        )
        self.assertEqual(result["source"], "DERIV_PUBLIC")
        self.assertEqual(result["execution"], "DISABLED")

    def test_symbol_mismatch(self):
        with self.assertRaises(DerivMarketDataError):
            parse_tick({"msg_type": "tick", "tick": {"symbol": "frxGBPUSD", "quote": 1.2, "epoch": 1790000000}}, "frxEURUSD")

    def test_candle_request_is_read_only_and_bounded(self):
        self.assertEqual(
            candles_request("frxEURUSD", count=100, granularity=300),
            {
                "ticks_history": "frxEURUSD",
                "end": "latest",
                "count": 100,
                "style": "candles",
                "granularity": 300,
            },
        )
        with self.assertRaises(DerivMarketDataError):
            candles_request("R_100")
        with self.assertRaises(DerivMarketDataError):
            candles_request("frxEURUSD", count=1001)

    def test_valid_candles_are_normalized(self):
        result = parse_candles(
            {
                "msg_type": "candles",
                "echo_req": {"ticks_history": "frxEURUSD"},
                "candles": [
                    {"epoch": 100, "open": "1.1", "high": "1.2",
                     "low": "1.0", "close": "1.15"},
                ],
            },
            "frxEURUSD",
        )

        self.assertEqual(result["source"], "DERIV_PUBLIC")
        self.assertEqual(result["execution"], "DISABLED")
        self.assertEqual(result["candles"][0]["close"], "1.15")

    def test_invalid_or_mismatched_candles_rejected(self):
        with self.assertRaises(DerivMarketDataError):
            parse_candles(
                {"error": {"code": "InvalidSymbol"}},
                "frxEURUSD",
            )
        with self.assertRaises(DerivMarketDataError):
            parse_candles(
                {
                    "msg_type": "candles",
                    "echo_req": {"ticks_history": "frxGBPUSD"},
                    "candles": [],
                },
                "frxEURUSD",
            )
        with self.assertRaises(DerivMarketDataError):
            parse_candles(
                {
                    "msg_type": "candles",
                    "candles": [
                        {"epoch": 100, "open": "1.1", "high": "1.0",
                         "low": "0.9", "close": "1.0"},
                    ],
                },
                "frxEURUSD",
            )

    def test_rejects_api_error(self):
        with self.assertRaises(DerivMarketDataError):
            parse_tick({"error": {"code": "InvalidSymbol"}}, "frxEURUSD")

    async def test_public_catalog_uses_current_endpoint_without_app_id(self):
        response = {
            "msg_type": "active_symbols",
            "active_symbols": [{
                "market": "forex",
                "underlying_symbol": "frxEURUSD",
                "underlying_symbol_name": "EUR/USD",
                "pip_size": 0.00001,
                "exchange_is_open": 1,
                "is_trading_suspended": 0,
            }],
        }
        socket = AsyncMock()
        socket.recv.return_value = json.dumps(response)
        context = AsyncMock()
        context.__aenter__.return_value = socket
        with patch("websockets.connect", return_value=context) as connect:
            result = await fetch_public_forex_markets()
        self.assertEqual(result["markets"][0]["pair"], "EURUSD")
        connect.assert_called_once_with(
            PUBLIC_WS_URL, open_timeout=8, close_timeout=3, max_size=262144
        )
        socket.send.assert_awaited_once_with('{"active_symbols": "brief"}')

    async def test_history_uses_current_public_endpoint_without_app_id(self):
        response = {
            "msg_type": "candles",
            "echo_req": {"ticks_history": "frxEURUSD"},
            "candles": [{
                "epoch": 100, "open": "1.1", "high": "1.2",
                "low": "1.0", "close": "1.15",
            }],
        }
        socket = AsyncMock()
        socket.recv.return_value = json.dumps(response)
        context = AsyncMock()
        context.__aenter__.return_value = socket
        with patch("websockets.connect", return_value=context) as connect:
            result = await fetch_public_candles("frxEURUSD", count=80, granularity=300)
        self.assertEqual(result["candles"][0]["close"], "1.15")
        connect.assert_called_once_with(
            PUBLIC_WS_URL, open_timeout=8, close_timeout=3, max_size=65536
        )
        socket.send.assert_awaited_once_with(json.dumps({
            "ticks_history": "frxEURUSD",
            "end": "latest",
            "count": 80,
            "style": "candles",
            "granularity": 300,
        }))

    async def test_single_tick_uses_current_public_endpoint_without_app_id(self):
        response = {
            "msg_type": "tick",
            "tick": {"symbol": "frxEURUSD", "quote": 1.0852, "epoch": 1790000000},
        }
        socket = AsyncMock()
        socket.recv.return_value = json.dumps(response)
        context = AsyncMock()
        context.__aenter__.return_value = socket
        with patch("websockets.connect", return_value=context) as connect:
            result = await fetch_public_tick("frxEURUSD")
        self.assertEqual(result["quote"], "1.0852")
        connect.assert_called_once_with(
            PUBLIC_WS_URL, open_timeout=8, close_timeout=3, max_size=65536
        )


if __name__ == "__main__":
    unittest.main()
