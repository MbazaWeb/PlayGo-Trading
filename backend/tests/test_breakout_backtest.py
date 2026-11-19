import json
import unittest

from app.breakout_backtest import BacktestInputError, backtest_breakout


def sample_candles():
    rows = []
    for index in range(5):
        rows.append({
            "epoch": 1_800_000_000 + index * 300,
            "open": "1.10000",
            "high": "1.10010",
            "low": "1.09990",
            "close": "1.10000",
        })
    rows.extend([
        {
            "epoch": 1_800_000_000 + 5 * 300,
            "open": "1.10000",
            "high": "1.10050",
            "low": "1.09990",
            "close": "1.10030",
        },
        {
            "epoch": 1_800_000_000 + 6 * 300,
            "open": "1.10030",
            "high": "1.10080",
            "low": "1.10020",
            "close": "1.10070",
        },
    ])
    return rows


class BreakoutBacktestTests(unittest.TestCase):
    def test_deterministic_replay_preserves_finalized_trade_under_future_extension(self):
        candles = sample_candles()
        candles[-1]["high"] = "1.10200"
        persisted_input = json.dumps({"candles": candles, "pair": "EURUSD", "lookback": 5})
        result = backtest_breakout(**json.loads(persisted_input))
        replay = backtest_breakout(**json.loads(persisted_input))
        self.assertEqual(replay, result)
        self.assertEqual(result["trades"], [{
            "side": "BUY",
            "entry_epoch": 1_800_001_800,
            "exit_epoch": 1_800_001_800,
            "entry_price": "1.10030",
            "exit_price": "1.101140",
            "units": 4544,
            "gross_pnl": "3.82",
            "estimated_costs": "0.32",
            "net_pnl": "3.50",
            "exit_reason": "TARGET",
        }])
        self.assertEqual(result["metrics"]["ending_balance"], "10003.50")

        extended = [*candles, {
            "epoch": candles[-1]["epoch"] + 300,
            "open": "1.10070",
            "high": "1.10100",
            "low": "1.09700",
            "close": "1.09720",
        }]
        after = backtest_breakout(extended, pair="EURUSD", lookback=5)
        self.assertEqual(after["trades"][0], result["trades"][0])

    def test_confirmed_breakout_enters_on_next_bar_and_reports_assumptions(self):
        result = backtest_breakout(
            sample_candles(), pair="EURUSD", lookback=5)

        self.assertEqual(result["execution"], "RESEARCH_ONLY")
        self.assertEqual(result["metrics"]["trade_count"], 1)
        self.assertEqual(result["trades"][0]["entry_epoch"], sample_candles()[6]["epoch"])
        self.assertEqual(result["cost_filter"]["status"], "ASSUMPTION_ONLY")
        self.assertIn("not a live liquidity check", result["cost_filter"]["message"])

    def test_stop_is_used_when_stop_and_target_cross_in_same_bar(self):
        candles = sample_candles()
        candles[6]["low"] = "1.10000"
        result = backtest_breakout(
            candles,
            pair="EURUSD",
            lookback=5,
            stop_atr_multiple="0.5",
            reward_risk="0.5",
        )

        self.assertEqual(result["trades"][0]["exit_reason"], "STOP")

    def test_spread_cost_filter_blocks_when_assumption_exceeds_limit(self):
        result = backtest_breakout(
            sample_candles(),
            pair="EURUSD",
            lookback=5,
            estimated_spread_pips="2",
            max_spread_pips="1.5",
        )

        self.assertFalse(result["cost_filter"]["eligible"])
        self.assertEqual(result["metrics"]["trade_count"], 0)

    def test_does_not_use_entry_bar_high_to_create_breakout_signal(self):
        rows = sample_candles()
        rows[5]["close"] = "1.10000"

        result = backtest_breakout(rows, pair="EURUSD", lookback=5)

        self.assertEqual(result["metrics"]["trade_count"], 0)

    def test_invalid_candle_and_unsupported_pair_are_rejected(self):
        invalid = sample_candles()
        invalid[0]["high"] = "1.09900"

        with self.assertRaises(BacktestInputError):
            backtest_breakout(invalid, pair="EURUSD", lookback=5)
        with self.assertRaises(BacktestInputError):
            backtest_breakout(sample_candles(), pair="USDJPY", lookback=5)


if __name__ == "__main__":
    unittest.main()
