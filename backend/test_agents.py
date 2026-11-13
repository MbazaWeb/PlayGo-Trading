"""Phase 2 pure strategy and regression tests (requires backend dependencies)."""
import unittest
from unittest.mock import patch
import agents
import main


class StrategyTests(unittest.TestCase):
    def test_short_history_never_trades(self):
        self.assertIsNone(agents.signal([1.0] * 15))

    def test_no_crossover_means_no_signal(self):
        self.assertIsNone(agents.signal([1.0] * 30))

    def test_expensive_spread_rejected(self):
        s = main.new_state()
        s["history"] = {"EURUSD": [1.0] * 30}
        s["quotes"]["EURUSD"]["bid"] = 1.0
        s["quotes"]["EURUSD"]["ask"] = 1.001
        self.assertIsNone(agents.create_signal(s, "EURUSD"))

    def test_signals_only_with_ema_cross(self):
        prices = [1.0] * 22 + [1.01]
        self.assertEqual(agents.signal(prices), "BUY")

    def test_paper_only_configuration(self):
        self.assertEqual(agents.options()["execution"], "PAPER")
        self.assertEqual(agents.options()["configured_feed"], "SYNTHETIC")

    def test_auto_cycle_paused_does_not_place_order(self):
        main.state.clear()
        main.state.update(main.new_state())
        with patch.object(main, "tick", return_value=main.snapshot()) as tick, \
             patch.object(main, "order") as order:
            result = agents.tick_cycle(main)
            tick.assert_called_once()
            order.assert_not_called()
            self.assertTrue(result["paused"])


if __name__ == "__main__":
    unittest.main()
