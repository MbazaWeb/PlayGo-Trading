"""Offline Phase 4 tests: SQL pagination, filtering, details, and owner authorization."""
import unittest
from unittest.mock import MagicMock, patch

from fastapi import HTTPException
from app import postgres_api
from app import postgres_demo_orders as orders


SAMPLE = {"_id": "test-order", "status": "FILLED",
          "request": {"pair": "EURUSD", "side": "BUY", "units": 100,
                      "bid": "1.0849", "ask": "1.0851", "slippage_pips": "0.2"},
          "fill": {"execution_id": "fake"}, "created_at": "2026-11-15T12:00:00+00:00",
          "updated_at": "2026-11-15T12:00:00+00:00",
          "fingerprint": "private-not-exposed"}


def fake_connection(rows):
    conn = MagicMock()
    cur = conn.cursor.return_value.__enter__.return_value
    cur.fetchone.side_effect = rows
    cur.fetchall.return_value = [(SAMPLE,)]
    return conn, cur


class OrderHistoryTests(unittest.TestCase):
    def test_history_pagination_and_filters(self):
        conn, cur = fake_connection([(1,)])
        result = orders.list_orders(conn, limit=20, offset=40, pair="EURUSD",
                                    side="BUY", status="FILLED",
                                    date_from="2026-11-01", date_to="2026-11-30")
        self.assertEqual((result["total"], result["offset"]), (1, 40))
        self.assertEqual(result["orders"][0]["client_order_id"], "test-order")
        self.assertNotIn("fingerprint", result["orders"][0])
        count_sql, count_params = cur.execute.call_args_list[0].args
        page_sql, page_params = cur.execute.call_args_list[1].args
        self.assertIn("count(*)", count_sql)
        self.assertIn("order by", page_sql)
        self.assertEqual(page_params[:-2], count_params)
        self.assertEqual(page_params[-2:], [20, 40])
        self.assertIn("EURUSD", count_params)
        self.assertIn("2026-11-30", count_params)

    def test_invalid_filters_rejected(self):
        for kwargs in ({"limit": 0}, {"offset": -1}, {"pair": "USDJPY"},
                       {"side": "INVALID"}, {"status": "EXECUTED"},
                       {"date_from": "bad"}, {"date_from": "2026-12-01",
                                             "date_to": "2026-11-01"}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                orders.list_orders(MagicMock(), **kwargs)

    def test_detail_found_and_missing(self):
        conn, cur = fake_connection([(SAMPLE,)])
        result = orders.get_order(conn, "test-order")
        self.assertEqual(result["status"], "FILLED")
        self.assertNotIn("fingerprint", result)
        self.assertEqual(cur.execute.call_args.args[1], (orders.COLLECTION, "test-order"))
        conn2, _ = fake_connection([None])
        self.assertIsNone(orders.get_order(conn2, "missing"))

    def test_owner_required_for_history_and_detail(self):
        with patch.object(postgres_api, "owner", side_effect=HTTPException(401, "Unauthorized")):
            for fn in (
                lambda: postgres_api.demo_order_history(authorization=""),
                lambda: postgres_api.demo_order_detail("test-order", authorization=""),
            ):
                with self.assertRaises(HTTPException) as caught:
                    fn()
                self.assertEqual(caught.exception.status_code, 401)

    def test_history_validation_returns_400(self):
        with patch.object(postgres_api, "owner", return_value="owner"), patch.object(
            postgres_api, "connect"
        ), patch.object(postgres_api.postgres_demo_orders, "list_orders",
                        side_effect=ValueError("invalid")):
            with self.assertRaises(HTTPException) as caught:
                postgres_api.demo_order_history(authorization="Bearer token")
            self.assertEqual(caught.exception.status_code, 400)

    def test_detail_not_found_returns_404(self):
        with patch.object(postgres_api, "owner", return_value="owner"), patch.object(
            postgres_api, "connect"
        ), patch.object(postgres_api.postgres_demo_orders, "get_order",
                        return_value=None):
            with self.assertRaises(HTTPException) as caught:
                postgres_api.demo_order_detail("missing", authorization="Bearer token")
            self.assertEqual(caught.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
