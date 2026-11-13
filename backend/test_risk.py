"""Deterministic paper-trading safety tests: no external MongoDB or OANDA."""
from copy import deepcopy
import unittest
from unittest.mock import patch

from fastapi import HTTPException
import main


class MemoryCollection:
    def replace_one(self, *_args, **_kwargs):
        return None


class RiskEngineTests(unittest.TestCase):
    def setUp(self):
        main.state.clear()
        main.state.update(main.new_state())
        main.state_collection = MemoryCollection()

    def tearDown(self):
        main.state_collection = None

    def test_paused_engine_rejects_orders(self):
        with self.assertRaises(HTTPException) as error:
            main.order(main.Order(pair="EURUSD", side="BUY"))
        self.assertEqual(error.exception.status_code, 403)
        self.assertEqual(main.state["positions"], [])

    def test_open_position_never_exceeds_unleveraged_equity(self):
        main.start()
        before = main.equity()
        main.order(main.Order(pair="EURUSD", side="BUY"))
        p = main.state["positions"][0]
        self.assertLessEqual(p["units"] * p["entry"], before)
        self.assertEqual(p["pair"], "EURUSD")

    def test_duplicate_pair_is_rejected(self):
        main.start()
        main.order(main.Order(pair="EURUSD", side="BUY"))
        with self.assertRaises(HTTPException):
            main.order(main.Order(pair="EURUSD", side="SELL"))
        self.assertEqual(len(main.state["positions"]), 1)

    def test_usdjpy_orders_remain_disabled(self):
        main.start()
        with self.assertRaises(HTTPException):
            main.order(main.Order(pair="USDJPY", side="BUY"))
        self.assertEqual(main.state["positions"], [])

    def test_daily_equity_drawdown_blocks_restart(self):
        main.state["balance"] = 9700
        with self.assertRaises(HTTPException) as error:
            main.start()
        self.assertEqual(error.exception.status_code, 403)

    def test_manual_close_creates_virtual_trade(self):
        main.start()
        main.order(main.Order(pair="GBPUSD", side="BUY"))
        p = deepcopy(main.state["positions"][0])
        main.close(p["id"])
        self.assertEqual(len(main.state["positions"]), 0)
        self.assertEqual(len(main.state["trades"]), 1)
        self.assertEqual(main.state["trades"][0]["reason"], "MANUAL")


if __name__ == "__main__":
    unittest.main()
