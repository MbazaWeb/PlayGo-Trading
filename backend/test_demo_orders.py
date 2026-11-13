"""Deterministic tests for durable, broker-free demo order intent handling."""
import unittest
from copy import deepcopy
from pymongo.errors import DuplicateKeyError
from demo_orders import (OrderConflict, PENDING, FILLED,
                         submit_demo_order, pending_orders, recover_pending)


class Cursor:
    def __init__(self, rows):
        self.rows = rows
    def sort(self, field, direction):
        self.rows.sort(key=lambda row: row[field], reverse=direction == -1)
        return self
    def limit(self, count):
        return self.rows[:count]


class FakeCollection:
    def __init__(self):
        self.rows = {}
    def insert_one(self, row):
        key = row["_id"]
        if key in self.rows:
            raise DuplicateKeyError("duplicate")
        self.rows[key] = deepcopy(row)
    def find_one(self, query):
        row = self.rows.get(query["_id"])
        return deepcopy(row) if row else None
    def update_one(self, query, update):
        row = self.rows.get(query["_id"])
        if row and row["status"] == query["status"]:
            row.update(deepcopy(update["$set"]))
    def find(self, query):
        return Cursor([deepcopy(row) for row in self.rows.values()
                       if row["mode"] == query["mode"] and row["status"] == query["status"]])


class DurableDemoOrderTests(unittest.TestCase):
    def setUp(self):
        self.db = FakeCollection()
        self.order = dict(client_order_id="test-1", pair="EURUSD", side="BUY",
                          units=1000, bid="1.10000", ask="1.10020")

    def test_duplicate_replay_has_same_execution_id(self):
        first = submit_demo_order(self.db, **self.order)
        second = submit_demo_order(self.db, **self.order)
        self.assertEqual(first, second)
        self.assertEqual(first["status"], FILLED)
        self.assertEqual(len(self.db.rows), 1)

    def test_conflicting_id_rejected(self):
        submit_demo_order(self.db, **self.order)
        with self.assertRaises(OrderConflict):
            submit_demo_order(self.db, **{**self.order, "units": 2000})

    def test_pending_order_recovers_without_second_intent(self):
        first = submit_demo_order(self.db, **self.order)
        row = self.db.rows["test-1"]
        row["status"] = PENDING
        row.pop("fill", None)
        self.assertEqual(len(pending_orders(self.db)), 1)
        recovered = recover_pending(self.db)
        self.assertEqual(recovered["recovered"], ["test-1"])
        self.assertEqual(len(self.db.rows), 1)
        self.assertEqual(self.db.rows["test-1"]["fill"], first["fill"])


if __name__ == "__main__":
    unittest.main()
