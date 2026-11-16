"""Offline safety checks for the Deriv public tick adapter."""
import unittest
from unittest.mock import patch
from app.deriv_market_data import DerivMarketDataError, parse_tick, tick_request, fetch_public_tick


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

    def test_rejects_api_error(self):
        with self.assertRaises(DerivMarketDataError):
            parse_tick({"error": {"code": "InvalidSymbol"}}, "frxEURUSD")

    async def test_app_id_required(self):
        with patch.dict("os.environ", {"DERIV_APP_ID": ""}):
            with self.assertRaises(DerivMarketDataError):
                await fetch_public_tick("frxEURUSD")


if __name__ == "__main__":
    unittest.main()
