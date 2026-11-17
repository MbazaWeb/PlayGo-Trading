import unittest
from decimal import Decimal

from app.demo_execution import DemoExecutionEngine, DemoOrderError


class DemoExecutionPricingTests(unittest.TestCase):

    def test_buy_fill_price(self):
        fill = DemoExecutionEngine("0.2").execute(
            client_order_id="buy-001",
            pair="EURUSD",
            side="BUY",
            units=1000,
            bid="1.08490",
            ask="1.08510",
        )
        self.assertEqual(Decimal(fill["filled_price"]), Decimal("1.08512"))
        self.assertEqual(fill["estimated_spread_cost_usd"], "0.20")

    def test_sell_fill_price(self):
        fill = DemoExecutionEngine("0.2").execute(
            client_order_id="sell-001",
            pair="EURUSD",
            side="SELL",
            units=1000,
            bid="1.08490",
            ask="1.08510",
        )
        self.assertEqual(Decimal(fill["filled_price"]), Decimal("1.08488"))

    def test_zero_slippage(self):
        fill = DemoExecutionEngine("0").execute(
            client_order_id="zero-001",
            pair="GBPUSD",
            side="BUY",
            units=100,
            bid="1.25000",
            ask="1.25020",
        )
        self.assertEqual(Decimal(fill["filled_price"]), Decimal("1.25020"))

    def test_excessive_slippage_rejected(self):
        with self.assertRaises(DemoOrderError):
            DemoExecutionEngine("5.1")

    def test_negative_slippage_rejected(self):
        with self.assertRaises(DemoOrderError):
            DemoExecutionEngine("-0.1")

    def test_invalid_quote_rejected(self):
        with self.assertRaises(DemoOrderError):
            DemoExecutionEngine().execute(
                client_order_id="quote-001",
                pair="EURUSD",
                side="BUY",
                units=100,
                bid="1.10000",
                ask="1.09900",
            )

    def test_invalid_quantity_rejected(self):
        with self.assertRaises(DemoOrderError):
            DemoExecutionEngine().execute(
                client_order_id="quantity-001",
                pair="EURUSD",
                side="BUY",
                units=0,
                bid="1.10000",
                ask="1.10020",
            )

    def test_nonfinite_price_rejected(self):
        with self.assertRaises(DemoOrderError):
            DemoExecutionEngine().execute(
                client_order_id="nan-001",
                pair="EURUSD",
                side="BUY",
                units=100,
                bid="NaN",
                ask="1.10020",
            )


if __name__ == "__main__":
    unittest.main()