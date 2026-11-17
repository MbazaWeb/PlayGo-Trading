"""Offline safety checks for the Deriv public tick adapter."""
import unittest
from unittest.mock import patch
from app.deriv_market_data import (
    DerivMarketDataError,
    candles_request,
    fetch_public_candles,
    parse_candles,
    parse_tick,
    tick_request,
    fetch_public_tick,
)


class DerivMarketDataTests(unittest.IsolatedAsyncioTestCase):
    def test_request_has_no_auth_or_trade_operation(self):
        self.assertEqual(tick_request("frxEURUSD"), {"ticks": "frxEURUSD", "subscribe": 0})

    def test_symbol_allowlist(self):
        with self.assertRaises(DerivMarketDataError):
            tick_request("R_100")

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

    async def test_app_id_required(self):
        with patch.dict("os.environ", {"DERIV_APP_ID": ""}):
            with self.assertRaises(DerivMarketDataError):
                await fetch_public_tick("frxEURUSD")

    async def test_history_app_id_required(self):
        with patch.dict("os.environ", {"DERIV_APP_ID": ""}):
            with self.assertRaises(DerivMarketDataError):
                await fetch_public_candles("frxEURUSD")


if __name__ == "__main__":
    unittest.main()
