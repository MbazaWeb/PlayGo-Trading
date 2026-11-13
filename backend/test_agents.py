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

    def test_strategy_monitor_holds_while_warming_up(self):
        rows = agents.diagnostics(main.new_state())
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(row["signal"] == "HOLD" for row in rows))
        self.assertTrue(all(row["reason"] == "WARMING_UP" for row in rows))

    def test_strategy_monitor_reports_buy_crossover(self):
        state = main.new_state()
        state["history"]["EURUSD"] = [1.0] * 22 + [1.01]
        row = next(row for row in agents.diagnostics(state) if row["pair"] == "EURUSD")
        self.assertEqual(row["signal"], "BUY")
        self.assertEqual(row["reason"], "CROSSOVER")

    def test_strategy_monitor_blocks_wide_spread(self):
        state = main.new_state()
        state["history"]["EURUSD"] = [1.0] * 22 + [1.01]
        state["quotes"]["EURUSD"]["ask"] = state["quotes"]["EURUSD"]["bid"] + 0.001
        row = next(row for row in agents.diagnostics(state) if row["pair"] == "EURUSD")
        self.assertEqual(row["signal"], "HOLD")
        self.assertEqual(row["reason"], "SPREAD_TOO_WIDE")

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
