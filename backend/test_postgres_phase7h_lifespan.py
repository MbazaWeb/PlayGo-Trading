"""Phase 7H.1: application lifespan integration contract (no live DB).

TestClient enters the real FastAPI lifespan. PostgreSQL operations are mocked
so these tests cannot mutate real databases or trading state.
"""
import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
import postgres_api


class DeploymentLifespanTests(unittest.TestCase):
    def test_startup_checks_schema_before_initialization(self):
        events = []
        conn = MagicMock()
        with patch.object(postgres_api, "connect") as connect, \
             patch.object(postgres_api.postgres_readiness, "check",
                          side_effect=lambda c: events.append("readiness")), \
             patch.object(postgres_api.postgres_accounting, "initialize",
                          side_effect=lambda c: events.append("accounting")), \
             patch.object(postgres_api.postgres_state, "initialize",
                          side_effect=lambda c: events.append("state")), \
             patch.object(postgres_api.postgres_accounting, "post",
                          side_effect=lambda c, **kw: events.append("synthetic_capital")) as post:
            connect.return_value.__enter__.return_value = conn
            with TestClient(postgres_api.app) as client:
                live = client.get("/api/health")
                self.assertEqual(live.status_code, 200)
                self.assertEqual(live.json()["execution"], "DISABLED")
                self.assertFalse(live.json()["eligible"])
            self.assertEqual(events, ["readiness", "accounting", "state",
                                      "synthetic_capital"])
            post.assert_called_once()
            self.assertEqual(post.call_args.kwargs["kind"], "CAPITAL_IN")
            self.assertEqual(post.call_args.kwargs["reference"],
                             "SYNTHETIC_ACCOUNT_INITIALIZATION")
            connect.return_value.__exit__.assert_called_once()

    def test_readiness_failure_prevents_any_startup_writes(self):
        with patch.object(postgres_api, "connect") as connect, \
             patch.object(postgres_api.postgres_readiness, "check",
                          side_effect=RuntimeError("schema missing")), \
             patch.object(postgres_api.postgres_accounting, "initialize") as accounting, \
             patch.object(postgres_api.postgres_state, "initialize") as state, \
             patch.object(postgres_api.postgres_accounting, "post") as post:
            connect.return_value.__enter__.return_value = MagicMock()
            with self.assertRaisesRegex(RuntimeError, "schema missing"):
                with TestClient(postgres_api.app):
                    pass
            accounting.assert_not_called()
            state.assert_not_called()
            post.assert_not_called()

    def test_accounting_initialization_failure_blocks_state_and_post(self):
        with patch.object(postgres_api, "connect") as connect, \
             patch.object(postgres_api.postgres_readiness, "check"), \
             patch.object(postgres_api.postgres_accounting, "initialize",
                          side_effect=RuntimeError("accounting unavailable")), \
             patch.object(postgres_api.postgres_state, "initialize") as state, \
             patch.object(postgres_api.postgres_accounting, "post") as post:
            connect.return_value.__enter__.return_value = MagicMock()
            with self.assertRaisesRegex(RuntimeError, "accounting unavailable"):
                with TestClient(postgres_api.app):
                    pass
            state.assert_not_called()
            post.assert_not_called()

    def test_public_registration_disabled_without_database_access(self):
        with patch.object(postgres_api, "connect",
                          side_effect=AssertionError("unexpected DB access")):
            client = TestClient(postgres_api.app)
            response = client.post("/api/identity/register", json={})
        self.assertEqual(response.status_code, 403)

    def test_owner_bootstrap_rejected_outside_local_without_database_access(self):
        with patch.dict("os.environ", {"PLAYGO_ENV": "production",
                                      "PLAYGO_OWNER_BOOTSTRAP_SECRET": ""}), \
             patch.object(postgres_api, "connect",
                          side_effect=AssertionError("unexpected DB access")):
            response = TestClient(postgres_api.app).post(
                "/api/identity/bootstrap-owner",
                json={"username": "owner123", "password": "not-a-real-password"})
        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
