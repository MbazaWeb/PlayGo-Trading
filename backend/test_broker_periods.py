"""Unit tests for broker isolation and calendar-window virtual P&L."""
import unittest
from datetime import datetime, timezone
from broker import BrokerUnavailable, execution_policy, reject_live_execution
from periods import summarize, window_start


class BrokerSafetyTests(unittest.TestCase):
    def test_live_trading_is_unavailable(self):
        policy = execution_policy()
        self.assertFalse(policy["real_money_enabled"])
        self.assertFalse(policy["broker"]["live_orders"])
        with self.assertRaises(BrokerUnavailable):
            reject_live_execution(pair="EURUSD", units=100)

    def test_period_boundaries_and_legacy_trades(self):
        now = datetime(2026, 11, 13, 12, 30, tzinfo=timezone.utc)
        trades = [
            {"closed_at": "2026-11-13T12:30:05+00:00", "pnl": 5},
            {"closed_at": "2026-11-13T11:55:00+00:00", "pnl": -2},
            {"closed_at": "2026-11-12T15:00:00+00:00", "pnl": 10},
            {"pnl": 1000},
        ]
        result = summarize(trades, now)
        self.assertEqual(result["windows"]["hour"]["realized_pnl_usd"], 5)
        self.assertEqual(result["windows"]["day"]["realized_pnl_usd"], 3)
        self.assertEqual(result["windows"]["week"]["realized_pnl_usd"], 13)
        self.assertEqual(result["legacy_trades_without_valid_close_time"], 1)

    def test_week_starts_on_monday_utc(self):
        now = datetime(2026, 11, 13, 12, 30, tzinfo=timezone.utc)
        self.assertEqual(window_start("week", now).day, 9)

    def test_future_trade_is_not_counted(self):
        now = datetime(2026, 11, 13, 12, 30, tzinfo=timezone.utc)
        result = summarize([{"closed_at": "2026-11-14T00:00:00+00:00", "pnl": 100}], now)
        self.assertEqual(result["windows"]["month"]["closed_trades"], 0)


if __name__ == "__main__":
    unittest.main()
