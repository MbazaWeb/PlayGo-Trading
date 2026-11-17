import unittest

from app.demo_execution import DemoExecutionEngine, DemoOrderError


class DemoOrderIdTests(unittest.TestCase):

    def test_whitespace_only_id_rejected(self):
        with self.assertRaises(DemoOrderError):
            DemoExecutionEngine().execute(
                client_order_id="   ",
                pair="EURUSD", side="BUY", units=100,
                bid="1.08490", ask="1.08510"
            )

    def test_non_string_id_rejected(self):
        with self.assertRaises(DemoOrderError):
            DemoExecutionEngine().execute(
                client_order_id=123,
                pair="EURUSD", side="BUY", units=100,
                bid="1.08490", ask="1.08510"
            )

    def test_valid_id_accepted(self):
        result = DemoExecutionEngine().execute(
            client_order_id="playgo-order-001",
            pair="EURUSD", side="BUY", units=100,
            bid="1.08490", ask="1.08510"
        )
        self.assertEqual(result["status"], "FILLED")


if __name__ == "__main__":
    unittest.main()
