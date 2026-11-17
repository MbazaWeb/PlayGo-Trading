"""Phase 6A: deterministic offline risk and mark-to-market tests."""
import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from fastapi import HTTPException
from app import postgres_positions as p
from app import postgres_api


def state(**overrides):
    data = {"paused": False, "balance": 10000, "day_start_balance": 10000,
            "positions": [], "loss_streak": 0, "risk_lock_reason": None,
            "revision": 2, "quotes": {"EURUSD": {"bid": 1.0849, "ask": 1.0851}}}
    data.update(overrides)
    return data


class PositionRiskTests(unittest.TestCase):
    def test_buy_preview(self):
        x = p.validate_open(state(), pair="EURUSD", side="BUY",
                            units=1000, entry_price="1.0851", stop_loss="1.0800")
        self.assertEqual(x["notional_usd"], "1085.1000")
        self.assertEqual(x["risk_usd"], "5.1000")

    def test_sell_preview(self):
        x = p.validate_open(state(), pair="GBPUSD", side="SELL",
                            units=1000, entry_price="1.26", stop_loss="1.27")
        self.assertEqual(x["risk_usd"], "10.00")

    def test_reject_paused(self):
        with self.assertRaises(p.RiskRejected):
            p.validate_open(state(paused=True), pair="EURUSD", side="BUY",
                            units=100, entry_price="1.1", stop_loss="1.0")

    def test_reject_excessive_risk(self):
        with self.assertRaises(p.RiskRejected):
            p.validate_open(state(), pair="EURUSD", side="BUY",
                            units=4000, entry_price="1.1", stop_loss="1.0")

    def test_reject_nonfinite(self):
        with self.assertRaises(p.RiskRejected):
            p.validate_open(state(), pair="EURUSD", side="BUY",
                            units=100, entry_price="NaN", stop_loss="1.0")

    def test_reject_exposure(self):
        with self.assertRaises(p.RiskRejected):
            p.validate_open(state(), pair="EURUSD", side="BUY",
                            units=5000, entry_price="1.1", stop_loss="1.09")

    def test_reject_daily_drawdown(self):
        with self.assertRaises(p.RiskRejected):
            p.validate_open(state(balance=9700), pair="EURUSD", side="BUY",
                            units=100, entry_price="1.1", stop_loss="1.09")

    def test_mark_buy_uses_bid(self):
        result = p.mark_to_market({"pair": "EURUSD", "side": "BUY",
                                   "units": 1000, "entry_price": "1.0850"},
                                  {"bid": "1.0860", "ask": "1.0862"})
        self.assertEqual(result["pnl_usd"], "1.00")

    def test_mark_sell_uses_ask(self):
        result = p.mark_to_market({"pair": "EURUSD", "side": "SELL",
                                   "units": 1000, "entry_price": "1.0850"},
                                  {"bid": "1.0838", "ask": "1.0840"})
        self.assertEqual(result["pnl_usd"], "1.00")

    def test_daily_loss_usage_counts_closed_losses_and_open_risk(self):
        now = datetime(2026, 11, 17, 12, 0, tzinfo=timezone.utc)
        current = state(
            trades=[{"closed_at": now.isoformat(), "pnl": "-1.25"}],
            positions=[{"pair": "EURUSD", "side": "BUY", "units": 50,
                        "entry_price": "1.0850", "stop_loss": "1.0750"}],
        )
        usage = p.daily_loss_usage(current, now=now)
        self.assertEqual(usage["realized_losses_usd"], "1.25")
        self.assertEqual(usage["open_risk_usd"], "0.50")
        self.assertEqual(usage["remaining_usd"], "0.25")

    def test_daily_loss_usage_ignores_closed_losses_from_prior_utc_day(self):
        now = datetime(2026, 11, 17, 0, 5, tzinfo=timezone.utc)
        current = state(trades=[{
            "closed_at": "2026-11-16T23:59:59+00:00", "pnl": "-2.00",
        }])
        usage = p.daily_loss_usage(current, now=now)
        self.assertEqual(usage["used_usd"], "0.00")
        self.assertEqual(usage["remaining_usd"], "2.00")

    def test_daily_loss_usage_fails_closed_for_naive_trade_timestamp(self):
        current = state(trades=[{"closed_at": "2026-11-17T12:00:00", "pnl": "-1"}])
        with self.assertRaisesRegex(p.RiskRejected, "timezone"):
            p.daily_loss_usage(current)

    def test_preview_requires_owner(self):
        with patch.object(postgres_api, "owner", side_effect=HTTPException(401, "Unauthorized")):
            with self.assertRaises(HTTPException) as caught:
                postgres_api.preview_paper_position(
                    postgres_api.PaperPositionPreview(
                        pair="EURUSD", side="BUY", units=100,
                        stop_loss="1.0800"), authorization="")
        self.assertEqual(caught.exception.status_code, 401)


if __name__ == "__main__":
    unittest.main()
