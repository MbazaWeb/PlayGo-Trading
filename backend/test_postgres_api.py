"""Isolated HTTP route contract tests; no database or broker access."""
import unittest
from unittest.mock import patch

from fastapi import HTTPException

import postgres_api
import postgres_ledger


class PostgresApiContractTests(unittest.TestCase):
    def test_public_registration_is_disabled(self):
        with self.assertRaises(HTTPException) as caught:
            postgres_api.register_disabled()
        self.assertEqual(caught.exception.status_code, 403)

    def test_state_requires_owner_authentication(self):
        with patch.object(postgres_api, "owner", side_effect=HTTPException(401, "Unauthorized")):
            with self.assertRaises(HTTPException) as caught:
                postgres_api.paper_state(authorization="")
        self.assertEqual(caught.exception.status_code, 401)

    def test_state_control_rejects_stale_revision(self):
        payload = postgres_api.PaperControlRequest(expected_revision=0, paused=False)
        with patch.object(postgres_api, "owner", return_value="test-owner"), patch.object(
            postgres_api, "connect"
        ) as connect, patch.object(
            postgres_api.postgres_state, "set_paused",
            side_effect=postgres_ledger.StaleStateError("stale"),
        ):
            with self.assertRaises(HTTPException) as caught:
                postgres_api.paper_control(payload, authorization="Bearer test")
        self.assertEqual(caught.exception.status_code, 409)
        connect.assert_called_once()

    def test_cycle_is_observation_only(self):
        payload = postgres_api.PaperCycleRequest(expected_revision=2)
        with patch.object(postgres_api, "owner", return_value="test-owner"), patch.object(
            postgres_api, "connect"
        ), patch.object(
            postgres_api.postgres_cycle, "run_cycle",
            return_value={"revision": 3, "paused": False},
        ):
            result = postgres_api.synthetic_cycle(payload, authorization="Bearer test")
        self.assertEqual(result["execution"], "OBSERVATION_ONLY")
        self.assertEqual(result["state"]["revision"], 3)

    def test_invalid_order_limit_rejected_before_db(self):
        with patch.object(postgres_api, "owner", return_value="test-owner"):
            with self.assertRaises(HTTPException) as caught:
                postgres_api.pending_demo_orders(limit=201, authorization="Bearer test")
        self.assertEqual(caught.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
