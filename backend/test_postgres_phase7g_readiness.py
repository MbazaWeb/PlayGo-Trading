"""Phase 7G.2 liveness, readiness, and startup failure isolation tests."""
import unittest
from contextlib import asynccontextmanager
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

import postgres_api
import postgres_readiness


class ReadinessTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(postgres_api.app)

    def test_liveness_is_not_readiness(self):
        with patch.object(postgres_api, "connect", side_effect=AssertionError("no DB call")):
            response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.assertFalse(response.json()["eligible"])
        self.assertEqual(response.json()["execution"], "DISABLED")

    def test_database_unavailable_is_sanitized_and_fail_closed(self):
        with patch.object(postgres_api, "connect",
                          side_effect=RuntimeError("password=PRIVATE_VALUE")):
            response = self.client.get("/api/ready")
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("PRIVATE_VALUE", response.text)
        self.assertFalse(response.json()["detail"]["ready"])
        self.assertEqual(response.json()["detail"]["execution"], "DISABLED")

    def test_missing_schema_fails_closed(self):
        conn = MagicMock()
        cur = conn.cursor.return_value.__enter__.return_value
        cur.fetchone.side_effect = [(1,), (None,)]
        with patch.object(postgres_api, "connect") as connect:
            connect.return_value.__enter__.return_value = conn
            response = self.client.get("/api/ready")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"]["database"], "UNAVAILABLE")

    def test_schema_present_is_ready_but_never_trade_eligible(self):
        conn = MagicMock()
        cur = conn.cursor.return_value.__enter__.return_value
        cur.fetchone.side_effect = [(1,), ("playgo_private.owners",),
                                    ("playgo_private.documents",)]
        with patch.object(postgres_api, "connect") as connect:
            connect.return_value.__enter__.return_value = conn
            response = self.client.get("/api/ready")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ready"])
        self.assertFalse(response.json()["eligible"])
        self.assertFalse(response.json()["automation_enabled"])
        self.assertEqual(response.json()["execution"], "DISABLED")

    def test_startup_missing_schema_prevents_initialization(self):
        conn = MagicMock()
        cur = conn.cursor.return_value.__enter__.return_value
        cur.fetchone.side_effect = [(1,), (None,)]
        with patch.object(postgres_api, "connect") as connect, \
             patch.object(postgres_api.postgres_accounting, "initialize") as initialize:
            connect.return_value.__enter__.return_value = conn
            with self.assertRaises(RuntimeError):
                with self.client:
                    pass
            initialize.assert_not_called()


if __name__ == "__main__":
    unittest.main()
