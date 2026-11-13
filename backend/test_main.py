import asyncio
from copy import deepcopy
import os
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from pymongo.errors import AutoReconnect

import main


class FakeCollection:
    documents = {}
    fail_writes = False

    def find_one(self, query):
        document = self.documents.get(query["_id"])
        return deepcopy(document) if document else None

    def insert_one(self, document):
        self.documents[document["_id"]] = deepcopy(document)

    def replace_one(self, query, document, upsert=False):
        if self.fail_writes:
            raise AutoReconnect("simulated database outage")
        self.documents[query["_id"]] = deepcopy(document)


class FakeDatabase:
    def __getitem__(self, _name):
        return FakeCollection()


class FakeAdmin:
    def command(self, _command):
        return {"ok": 1}


class FakeMongoClient:
    def __init__(self, *_args, **_kwargs):
        self.admin = FakeAdmin()
        self.closed = False

    def __getitem__(self, _name):
        return FakeDatabase()

    def close(self):
        self.closed = True


class MongoPersistenceTests(unittest.TestCase):
    def setUp(self):
        FakeCollection.documents.clear()
        FakeCollection.fail_writes = False
        main.state_collection = None
        main.mongo_client = None
        main.state.clear()
        main.state.update(main.new_state())

    def test_state_persists_and_is_restored_on_startup(self):
        async def run():
            with patch.dict(
                os.environ,
                {
                    "MONGODB_URI": "mongodb://localhost/test",
                    "MONGODB_DATABASE": "playgo_test",
                },
            ), patch.object(main, "MongoClient", FakeMongoClient):
                async with main.lifespan(main.app):
                    main.tick()
                    self.assertEqual(main.state["ticks"], 1)

                main.state["ticks"] = 99
                async with main.lifespan(main.app):
                    self.assertEqual(main.state["ticks"], 1)

        asyncio.run(run())

    def test_failed_write_rolls_back_state(self):
        main.state_collection = FakeCollection()
        FakeCollection.fail_writes = True

        with self.assertRaises(HTTPException) as raised:
            main.start()

        self.assertEqual(raised.exception.status_code, 503)
        self.assertTrue(main.state["paused"])
        self.assertEqual(main.state["logs"], [])



class PerformanceTests(unittest.TestCase):
    def setUp(self):
        main.state.clear()
        main.state.update(main.new_state())

    def test_pair_analytics_uses_closed_trades_only(self):
        main.state["trades"] = [
            {"pair": "EURUSD", "pnl": 15.0},
            {"pair": "EURUSD", "pnl": -5.0},
            {"pair": "GBPUSD", "pnl": 7.0},
        ]
        rows = {row["pair"]: row for row in main.trading_analytics()["pair_performance"]}
        self.assertEqual(rows["EURUSD"]["realized_pnl"], 10.0)
        self.assertEqual(rows["EURUSD"]["win_rate_pct"], 50.0)
        self.assertEqual(rows["GBPUSD"]["closed_trades"], 1)

    def test_observed_drawdown_uses_equity_samples(self):
        main.state["equity_history"] = [
            {"time": "t1", "equity": 10500},
            {"time": "t2", "equity": 9975},
        ]
        result = main.trading_analytics()
        self.assertEqual(result["max_observed_drawdown_pct"], 5.0)

    def test_equity_samples_are_bounded(self):
        main.state["equity_history"] = [{"time": "old", "equity": 10000}] * 500
        main.record_equity_sample()
        self.assertEqual(len(main.state["equity_history"]), 500)

    def test_decision_timeline_categorizes_persisted_events(self):
        main.state["logs"] = [
            {"id": "a", "time": "2026-11-13T10:00:00+00:00",
             "agent": "Risk Checker", "message": "Approved EURUSD"},
            {"id": "b", "time": "2026-11-13T09:59:00+00:00",
             "agent": "Strategy", "message": "BUY crossover"},
        ]
        events = main.decision_timeline()
        self.assertEqual([event["category"] for event in events], ["RISK", "SIGNAL"])
        self.assertEqual(events[0]["id"], "a")

    def test_empty_account_metrics(self):
        metrics = main.performance()
        self.assertEqual(metrics["closed_trades"], 0)
        self.assertEqual(metrics["win_rate_pct"], 0)
        self.assertEqual(metrics["net_pnl"], 0)

    def test_realized_win_rate_excludes_open_positions(self):
        main.state["trades"] = [{"pnl": 20.0}, {"pnl": -10.0}, {"pnl": 0.0}]
        main.state["balance"] = 10010.0
        main.state["positions"] = []
        metrics = main.performance()
        self.assertEqual(metrics["closed_trades"], 3)
        self.assertEqual(metrics["wins"], 1)
        self.assertEqual(metrics["losses"], 1)
        self.assertEqual(metrics["win_rate_pct"], 33.33)
        self.assertEqual(metrics["realized_pnl"], 10.0)

if __name__ == "__main__":
    unittest.main()
