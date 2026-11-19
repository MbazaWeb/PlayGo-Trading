import unittest

from app.strategy_engine import (
    DEFAULT_STRATEGY_ID,
    SUPPORTED_STRATEGY_IDS,
    apply_manual_rules,
    evaluate_auto_strategy,
    evaluate_strategy,
    select_auto_strategy,
)


def candles_for(closes):
    return [
        {
            "epoch": (index + 1) * 300,
            "open": str(close),
            "high": str(close + 0.1),
            "low": str(close - 0.1),
            "close": str(close),
        }
        for index, close in enumerate(closes)
    ]


class StrategyEngineTests(unittest.TestCase):
    def test_supported_catalog_is_explicit_and_uses_ema_as_default(self):
        self.assertEqual(len(SUPPORTED_STRATEGY_IDS), 24)
        self.assertIn(DEFAULT_STRATEGY_ID, SUPPORTED_STRATEGY_IDS)

    def test_every_supported_strategy_evaluates_a_sufficient_closed_candle_series(self):
        candles = candles_for([100] * 100)
        for strategy_id in SUPPORTED_STRATEGY_IDS:
            with self.subTest(strategy_id=strategy_id):
                result = evaluate_strategy(strategy_id, candles)
                self.assertTrue(result["ready"])
                self.assertIn(result["signal"], {"BUY", "SELL", "HOLD"})

    def test_ema_crossover_evaluates_only_the_latest_completed_bar(self):
        closes = [100 - index * 0.2 for index in range(29)] + [110]
        result = evaluate_strategy("ema-crossover", candles_for(closes))
        self.assertTrue(result["ready"])
        self.assertEqual(result["signal"], "BUY")
        self.assertIn("latest CLOSED candle", result["reason"])
        self.assertEqual(result["bar_time"], "1970-01-01T02:30:00+00:00")

    def test_breakout_strategy_uses_prior_closed_candle_range(self):
        closes = [100] * 25 + [102]
        candles = candles_for(closes)
        candles[-1]["open"] = "101.5"
        candles[-1]["high"] = "102.1"
        candles[-1]["low"] = "101.4"
        result = evaluate_strategy("donchian-channel-breakout", candles)
        self.assertTrue(result["ready"])
        self.assertEqual(result["signal"], "BUY")

    def test_research_only_and_invalid_candle_data_fail_closed(self):
        candles = candles_for([100] * 30)
        unsupported = evaluate_strategy("supertrend", candles)
        self.assertFalse(unsupported["ready"])
        self.assertEqual(unsupported["signal"], "HOLD")

        for strategy_id in ("triple-moving-average", "macd-crossover"):
            insufficient = evaluate_strategy(strategy_id, candles)
            self.assertFalse(insufficient["ready"])
            self.assertEqual(insufficient["signal"], "HOLD")

        for strategy_id, count in (("triple-moving-average", 47), ("macd-crossover", 39)):
            ready = evaluate_strategy(strategy_id, candles_for([100] * count))
            self.assertTrue(ready["ready"])
            self.assertEqual(ready["signal"], "HOLD")

        candles[5]["epoch"] = candles[4]["epoch"]
        invalid = evaluate_strategy(DEFAULT_STRATEGY_ID, candles)
        self.assertFalse(invalid["ready"])
        self.assertEqual(invalid["signal"], "HOLD")

    def test_auto_selector_chooses_breakout_and_stands_aside_without_setup(self):
        closes = [100] * 39 + [102]
        breakout_candles = candles_for(closes)
        breakout_candles[-1].update({"open": "101.5", "high": "102.1", "low": "101.4"})
        selection = select_auto_strategy(breakout_candles)
        self.assertEqual(selection["strategy_id"], "donchian-channel-breakout")

        no_setup = select_auto_strategy(candles_for([100] * 40))
        self.assertIsNone(no_setup["strategy_id"])
        self.assertTrue(no_setup["ready"])
        self.assertEqual(evaluate_auto_strategy(candles_for([100] * 40))["signal"], "HOLD")

    def test_auto_selector_chooses_trend_momentum_in_a_confirmed_trend(self):
        closes = [100 + 0.05 * index + [0, 0.3, 0.1, 0.2][index % 4] for index in range(60)]
        decision = evaluate_auto_strategy(candles_for(closes))
        self.assertEqual(decision["strategy_id"], "trend-momentum-hybrid")
        self.assertEqual(decision["signal"], "BUY")

    def test_auto_selector_skips_unusually_volatile_market(self):
        candles = candles_for([100] * 40)
        candles[-1]["high"] = "110"
        candles[-1]["low"] = "90"
        selection = select_auto_strategy(candles)
        self.assertIsNone(selection["strategy_id"])
        self.assertIn("Volatility filter", selection["reason"])

    def test_manual_rules_can_only_veto_automatic_signals(self):
        decision = {"signal": "BUY", "reason": "automatic", "bar_time": "2026-01-01T00:00:00+00:00"}
        blocked = apply_manual_rules(
            decision,
            {"rsi": 55, "atr_percent": 0.1},
            {"allow_signals": ["SELL"]},
        )
        self.assertEqual(blocked["signal"], "HOLD")
        self.assertIn("blocked", blocked["reason"])

        threshold_blocked = apply_manual_rules(
            decision,
            {"rsi": 49, "atr_percent": 0.1},
            {"allow_signals": ["BUY", "SELL"], "min_rsi": 50},
        )
        self.assertEqual(threshold_blocked["signal"], "HOLD")

        hold = {"signal": "HOLD", "reason": "no setup"}
        self.assertEqual(
            apply_manual_rules(hold, {}, {"allow_signals": ["BUY", "SELL"]}),
            hold,
        )


if __name__ == "__main__":
    unittest.main()
