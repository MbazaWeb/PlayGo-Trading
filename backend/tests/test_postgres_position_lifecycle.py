"""Phase 6B offline lifecycle tests. PostgreSQL integration remains required."""
import unittest
from contextlib import nullcontext
from copy import deepcopy
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from fastapi import HTTPException
from app import postgres_position_lifecycle as lifecycle
from app import postgres_positions as risk
from app import postgres_api
from app import postgres_ledger


def state(**kw):
    s = {"revision": 4, "feed_type": "SYNTHETIC", "paused": False,
         "risk_lock_reason": None, "loss_streak": 0,
         "day_start_date": datetime.now(timezone.utc).date().isoformat(),
         "day_start_balance": 10000, "balance": 10000,
         "starting_balance": 10000, "positions": [], "trades": [],
         "quotes": {"EURUSD": {"bid": 1.0850, "ask": 1.0852}}}
    s.update(kw)
    return s


def conn():
    c = MagicMock()
    c.transaction.return_value = nullcontext()
    return c


class LifecycleTests(unittest.TestCase):
    def test_open_persists_with_cas(self):
        c = conn()
        with patch.object(lifecycle.postgres_state, "load", return_value=state()), patch.object(
            lifecycle.postgres_state, "commit", return_value=5) as commit:
            result = lifecycle.open_position(
                c, position_id="p1", expected_revision=4, pair="EURUSD",
                side="BUY", units=1000, stop_loss="1.0800")
        self.assertEqual(result["status"], "OPEN")
        self.assertEqual(result["state_revision"], 5)
        self.assertEqual(commit.call_args.args[2]["positions"][0]["id"], "p1")

    def test_open_idempotent(self):
        p = {"id": "p1", "pair": "EURUSD", "side": "BUY", "units": 1000,
             "stop_loss": "1.0800", "entry_price": "1.0852"}
        with patch.object(lifecycle.postgres_state, "load", return_value=state(positions=[p])), patch.object(
            lifecycle.postgres_state, "commit") as commit:
            result = lifecycle.open_position(conn(), position_id="p1",
                expected_revision=1, pair="EURUSD", side="BUY",
                units=1000, stop_loss="1.0800")
        self.assertEqual(result["status"], "OPEN")
        commit.assert_not_called()

    def test_open_conflicting_id(self):
        p = {"id": "p1", "pair": "EURUSD", "side": "SELL",
             "units": 1000, "stop_loss": "1.0900"}
        with patch.object(lifecycle.postgres_state, "load", return_value=state(positions=[p])):
            with self.assertRaises(lifecycle.PositionConflict):
                lifecycle.open_position(conn(), position_id="p1",
                    expected_revision=4, pair="EURUSD", side="BUY",
                    units=1000, stop_loss="1.0800")

    def test_open_stale_revision(self):
        with patch.object(lifecycle.postgres_state, "load", return_value=state()):
            with self.assertRaises(postgres_ledger.StaleStateError):
                lifecycle.open_position(conn(), position_id="p1",
                    expected_revision=3, pair="EURUSD", side="BUY",
                    units=1000, stop_loss="1.0800")

    def test_close_gain_posts_verified_journal(self):
        p = {"id": "p1", "pair": "EURUSD", "side": "BUY",
             "units": 1000, "entry_price": "1.0840", "stop_loss": "1.0800"}
        with patch.object(lifecycle.postgres_state, "load", return_value=state(positions=[p])), patch.object(
            lifecycle.postgres_state, "commit", return_value=5) as commit, patch.object(
            lifecycle.postgres_accounting, "post") as post:
            result = lifecycle.close_position(conn(), position_id="p1", expected_revision=4)
        self.assertEqual(result["position"]["pnl"], "1.00")
        self.assertEqual(commit.call_args.args[2]["balance"], 10001.0)
        self.assertEqual(commit.call_args.args[2]["positions"], [])
        self.assertEqual(post.call_args.kwargs["amount_cents"], 100)
        self.assertEqual(post.call_args.kwargs["kind"], "REALIZED_GAIN")

    def test_close_loss_posts_journal(self):
        p = {"id": "p2", "pair": "EURUSD", "side": "SELL",
             "units": 1000, "entry_price": "1.0840", "stop_loss": "1.0900"}
        with patch.object(lifecycle.postgres_state, "load", return_value=state(positions=[p])), patch.object(
            lifecycle.postgres_state, "commit", return_value=5), patch.object(
            lifecycle.postgres_accounting, "post") as post:
            result = lifecycle.close_position(conn(), position_id="p2", expected_revision=4)
        self.assertEqual(result["position"]["pnl"], "-1.20")
        self.assertEqual(post.call_args.kwargs["kind"], "REALIZED_LOSS")
        self.assertEqual(post.call_args.kwargs["amount_cents"], 120)

    def test_close_idempotent(self):
        p = {"id": "p1", "status": "CLOSED", "pnl": "1.00"}
        with patch.object(lifecycle.postgres_state, "load", return_value=state(trades=[p])), patch.object(
            lifecycle.postgres_state, "commit") as commit, patch.object(
            lifecycle.postgres_accounting, "post") as post:
            result = lifecycle.close_position(conn(), position_id="p1", expected_revision=1)
        self.assertEqual(result["status"], "CLOSED")
        commit.assert_not_called()
        post.assert_not_called()

    def test_zero_pnl_skips_journal(self):
        p = {"id": "p1", "pair": "EURUSD", "side": "BUY",
             "units": 1000, "entry_price": "1.0850", "stop_loss": "1.0800"}
        with patch.object(lifecycle.postgres_state, "load", return_value=state(positions=[p])), patch.object(
            lifecycle.postgres_state, "commit", return_value=5), patch.object(
            lifecycle.postgres_accounting, "post") as post:
            result = lifecycle.close_position(conn(), position_id="p1", expected_revision=4)
        self.assertEqual(result["position"]["pnl"], "0.00")
        post.assert_not_called()

    def test_close_requires_owner(self):
        with patch.object(postgres_api, "owner", side_effect=HTTPException(401, "Unauthorized")):
            with self.assertRaises(HTTPException) as error:
                postgres_api.close_paper_position(
                    "p1", postgres_api.PaperPositionClose(expected_revision=4),
                    authorization="")
        self.assertEqual(error.exception.status_code, 401)


if __name__ == "__main__":
    unittest.main()
