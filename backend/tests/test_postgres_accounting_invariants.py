"""Offline accounting invariants for PostgreSQL migration.

These tests intentionally do not require database credentials. A separate
database integration run is still required before deployment.
"""
import unittest

from app.accounting_rules import apply_lines, journal_lines, opening_account, InsufficientFunds
from app.postgres_settlement import event_to_post


class PaperAccountingInvariantTests(unittest.TestCase):
    def test_opening_capital_matches_synthetic_account(self):
        balances = opening_account()["balances"]
        updated = apply_lines(balances, journal_lines("CAPITAL_IN", 1_000_000))
        self.assertEqual(updated["CASH"], 1_000_000)
        self.assertEqual(updated["CONTRIBUTED_CAPITAL"], 1_000_000)

    def test_double_entry_remains_balanced(self):
        for kind in ("CAPITAL_IN", "WITHDRAWAL", "REALIZED_GAIN", "REALIZED_LOSS", "FEE"):
            with self.subTest(kind=kind):
                lines = journal_lines(kind, 500)
                self.assertEqual(sum(line["debit_cents"] for line in lines),
                                 sum(line["credit_cents"] for line in lines))

    def test_loss_cannot_overdraw_paper_cash(self):
        funded = apply_lines(opening_account()["balances"],
                             journal_lines("CAPITAL_IN", 100))
        with self.assertRaises(InsufficientFunds):
            apply_lines(funded, journal_lines("REALIZED_LOSS", 101))

    def test_closed_trade_settlement_references_event(self):
        entry = event_to_post({
            "_id": "CLOSED:trade1", "trade_id": "trade1",
            "event_type": "PAPER_TRADE_CLOSED",
            "trade": {"id": "trade1", "pnl": "-12.34"},
        })
        self.assertEqual(entry, {
            "transaction_id": "TRADE:trade1", "kind": "REALIZED_LOSS",
            "amount_cents": 1234, "reference": "CLOSED:trade1",
        })


if __name__ == "__main__":
    unittest.main()
