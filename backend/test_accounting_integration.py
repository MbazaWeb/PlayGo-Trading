"""MongoDB integration test: run only against disposable replica-set database.

Set PLAYGO_TEST_MONGODB_URI and PLAYGO_TEST_MONGODB_DATABASE to an isolated
test database. NEVER point at production or a database with user funds.
Run: python -m unittest test_accounting_integration.py
"""
import os
import unittest
from uuid import uuid4
from pymongo import MongoClient
from accounting import opening_account, post, reconcile, ACCOUNT_ID, LedgerConflict
from settlement import settle_events


@unittest.skipUnless(os.getenv("PLAYGO_TEST_MONGODB_URI") and
                     os.getenv("PLAYGO_TEST_MONGODB_DATABASE", "").startswith("playgo_test_"),
                     "Set disposable PLAYGO_TEST_MONGODB_URI and playgo_test_* database")
class MongoAccountingIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = MongoClient(os.environ["PLAYGO_TEST_MONGODB_URI"], serverSelectionTimeoutMS=5000)
        cls.db = cls.client[os.environ["PLAYGO_TEST_MONGODB_DATABASE"]]
        cls.client.admin.command("ping")

    @classmethod
    def tearDownClass(cls):
        cls.client.close()

    def setUp(self):
        self.accounts = self.db["accounting_accounts_" + uuid4().hex]
        self.journals = self.db["accounting_journals_" + uuid4().hex]
        self.events = self.db["closed_events_" + uuid4().hex]
        self.accounts.insert_one(opening_account())

    def tearDown(self):
        self.accounts.drop()
        self.journals.drop()
        self.events.drop()

    def test_atomic_idempotent_reconciliation_and_settlement(self):
        post(self.accounts, self.journals, transaction_id="fund", kind="CAPITAL_IN",
             amount_cents=100000)
        self.events.insert_one({
            "_id": "CLOSED:trade1", "event_type": "PAPER_TRADE_CLOSED",
            "trade_id": "trade1", "recorded_at": "2026-11-13T10:00:00+00:00",
            "trade": {"id": "trade1", "pnl": 12.34},
        })
        first = settle_events(self.events, self.accounts, self.journals)
        second = settle_events(self.events, self.accounts, self.journals)
        self.assertFalse(first["failed"])
        self.assertFalse(second["failed"])
        self.assertEqual(self.accounts.find_one({"_id": ACCOUNT_ID})["balances"]["CASH"], 101234)
        self.assertEqual(self.journals.count_documents({}), 2)
        self.assertTrue(reconcile(self.accounts, self.journals)["consistent"])

    def test_reversal_restores_balance_and_rejects_second_reversal(self):
        post(self.accounts, self.journals, transaction_id="fund", kind="CAPITAL_IN",
             amount_cents=100000)
        post(self.accounts, self.journals, transaction_id="fee", kind="FEE",
             amount_cents=200)
        post(self.accounts, self.journals, transaction_id="reverse-fee",
             kind="REVERSAL", amount_cents=200, reference="fee")
        with self.assertRaises(LedgerConflict):
            post(self.accounts, self.journals, transaction_id="reverse-again",
                 kind="REVERSAL", amount_cents=200, reference="fee")
        self.assertEqual(self.accounts.find_one({"_id": ACCOUNT_ID})["balances"]["CASH"], 100000)
        self.assertTrue(reconcile(self.accounts, self.journals)["consistent"])


if __name__ == "__main__":
    unittest.main()
