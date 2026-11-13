"""Paper double-entry journal tests using fake transactional collections."""
import unittest
from contextlib import contextmanager
from copy import deepcopy
from pymongo.errors import DuplicateKeyError
from accounting import (ACCOUNT_ID, InsufficientFunds, LedgerConflict,
                        apply_lines, journal_lines, opening_account, post, reconcile)


class FakeSession:
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    @contextmanager
    def start_transaction(self):
        yield


class FakeClient:
    def start_session(self):
        return FakeSession()


class FakeDatabase:
    client = FakeClient()


class Cursor:
    def __init__(self, values):
        self.values = values
    def sort(self, field, direction):
        self.values.sort(key=lambda row: row[field], reverse=direction < 0)
        return self
    def limit(self, n):
        return self.values[:n]
    def __iter__(self):
        return iter(self.values)


class Accounts:
    database = FakeDatabase()
    def __init__(self):
        self.account = opening_account()
    def find_one(self, query):
        return deepcopy(self.account) if query["_id"] == ACCOUNT_ID else None
    def update_one(self, query, update, session):
        class Result:
            matched_count = 0
        result = Result()
        if query["revision"] == self.account["revision"]:
            self.account["balances"] = deepcopy(update["$set"]["balances"])
            self.account["revision"] += update["$inc"]["revision"]
            result.matched_count = 1
        return result


class Journals:
    def __init__(self):
        self.items = {}
    def find_one(self, query):
        return deepcopy(self.items.get(query["_id"]))
    def insert_one(self, row, session):
        if row["_id"] in self.items:
            raise DuplicateKeyError("Duplicate")
        self.items[row["_id"]] = deepcopy(row)
    def find(self, query):
        return Cursor([deepcopy(row) for row in self.items.values()
                       if row["account_id"] == query["account_id"]])


class AccountingTests(unittest.TestCase):
    def setUp(self):
        self.accounts = Accounts()
        self.journals = Journals()
    def record(self, id, kind, cents):
        return post(self.accounts, self.journals,
                    transaction_id=id, kind=kind, amount_cents=cents)

    def test_balanced_entries_all_types(self):
        for kind in ("CAPITAL_IN", "WITHDRAWAL", "REALIZED_GAIN", "REALIZED_LOSS", "FEE"):
            lines = journal_lines(kind, 100)
            self.assertEqual(sum(x["debit_cents"] for x in lines),
                             sum(x["credit_cents"] for x in lines))

    def test_capital_profit_loss_fees_withdrawal(self):
        self.record("1", "CAPITAL_IN", 100000)
        self.record("2", "REALIZED_GAIN", 2500)
        self.record("3", "REALIZED_LOSS", 1000)
        self.record("4", "FEE", 200)
        self.record("5", "WITHDRAWAL", 10000)
        balances = self.accounts.account["balances"]
        self.assertEqual(balances["CASH"], 91300)
        self.assertEqual(balances["CONTRIBUTED_CAPITAL"], 100000)
        self.assertEqual(balances["REALIZED_PNL"], 1500)
        self.assertEqual(balances["FEES"], 200)
        self.assertEqual(balances["WITHDRAWALS"], 10000)
        self.assertTrue(reconcile(self.accounts, self.journals)["consistent"])

    def test_withdrawal_cannot_overdraw(self):
        self.record("1", "CAPITAL_IN", 100)
        with self.assertRaises(InsufficientFunds):
            self.record("2", "WITHDRAWAL", 101)
        self.assertEqual(len(self.journals.items), 1)

    def test_idempotent_and_conflicting_id(self):
        first = self.record("same", "CAPITAL_IN", 100)
        self.assertEqual(first, self.record("same", "CAPITAL_IN", 100))
        self.assertEqual(self.accounts.account["revision"], 1)
        with self.assertRaises(LedgerConflict):
            self.record("same", "CAPITAL_IN", 200)

    def test_invalid_money(self):
        for amount in (0, -1, 1.5, True):
            with self.assertRaises(ValueError):
                journal_lines("FEE", amount)

    def test_tampering_detected(self):
        self.record("1", "CAPITAL_IN", 100)
        self.accounts.account["balances"]["CASH"] += 1
        result = reconcile(self.accounts, self.journals)
        self.assertFalse(result["consistent"])
        self.assertIn("BALANCE_MISMATCH", result["issues"])


if __name__ == "__main__":
    unittest.main()
