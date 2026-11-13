"""Transaction-boundary tests with lightweight fake MongoDB collections."""
import unittest
from contextlib import contextmanager
from ledger import StaleStateError, closed_trade_events, commit_state


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


class FakeStateCollection:
    database = FakeDatabase()
    def __init__(self, revision=0):
        self.revision = revision
        self.last_document = None
    def replace_one(self, query, document, upsert, session):
        assert not upsert
        class Result:
            matched_count = 0
        result = Result()
        if query["revision"] == self.revision:
            result.matched_count = 1
            self.last_document = document
            self.revision = document["revision"]
        return result


class FakeLedgerCollection:
    def __init__(self):
        self.events = []
    def insert_many(self, events, ordered, session):
        self.events.extend(events)


class LedgerTests(unittest.TestCase):
    def test_new_close_generates_one_event(self):
        previous = {"revision": 0, "trades": []}
        current = {"revision": 0, "trades": [{"id": "t1", "pnl": 12}]}
        self.assertEqual(len(closed_trade_events(previous, current)), 1)
        self.assertEqual(closed_trade_events(current, current), [])

    def test_commit_increments_revision_and_appends_event(self):
        state, events = FakeStateCollection(), FakeLedgerCollection()
        old = {"revision": 0, "trades": []}
        new = {"revision": 0, "trades": [{"id": "t1", "pnl": -4}]}
        self.assertEqual(commit_state(state, events, old, new), 1)
        self.assertEqual(state.last_document["revision"], 1)
        self.assertEqual(events.events[0]["trade_id"], "t1")

    def test_stale_writer_rejected(self):
        state, events = FakeStateCollection(revision=2), FakeLedgerCollection()
        with self.assertRaises(StaleStateError):
            commit_state(state, events, {"revision": 1, "trades": []},
                         {"revision": 1, "trades": []})
        self.assertFalse(events.events)


if __name__ == "__main__":
    unittest.main()
