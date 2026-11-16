"""Phase 7H.2 owner authentication API integration (mocked database).

No real credentials, database writes, or live trading.
"""
import os
import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from app import postgres_api
from app import postgres_identity


class AuthenticationIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(postgres_api.app)

    def test_valid_login_returns_session_token(self):
        connection = MagicMock()
        token = {"access_token": "a" * 64, "token_type": "bearer",
                 "expires_at": "2030-01-01T00:00:00+00:00"}
        with patch.object(postgres_api, "connect") as connect, \
             patch.object(postgres_identity, "login", return_value=token) as login:
            connect.return_value.__enter__.return_value = connection
            response = self.client.post("/api/identity/login",
                                        json={"username": "owner123",
                                              "password": "example-password"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), token)
        login.assert_called_once_with(connection, username="owner123",
                                      password="example-password")

    def test_invalid_credentials_return_401_without_details(self):
        with patch.object(postgres_api, "connect") as connect, \
             patch.object(postgres_identity, "login",
                          side_effect=postgres_identity.OwnerAuthError("Invalid credentials")):
            connect.return_value.__enter__.return_value = MagicMock()
            response = self.client.post("/api/identity/login",
                                        json={"username": "owner123",
                                              "password": "wrong-password"})
        self.assertEqual(response.status_code, 401)
        self.assertNotIn("password_hash", response.text)

    def test_protected_account_requires_valid_owner_session(self):
        with patch.object(postgres_api, "connect") as connect, \
             patch.object(postgres_identity, "verify_session",
                          side_effect=postgres_identity.OwnerAuthError("Invalid session")):
            connect.return_value.__enter__.return_value = MagicMock()
            denied = self.client.get("/api/identity/me/paper-account",
                                     headers={"Authorization": "Bearer invalid"})
        self.assertEqual(denied.status_code, 401)
        with patch.object(postgres_api, "connect") as connect, \
             patch.object(postgres_identity, "verify_session",
                          return_value="test-owner") as verify:
            connect.return_value.__enter__.return_value = MagicMock()
            allowed = self.client.get("/api/identity/me/paper-account",
                                      headers={"Authorization": "Bearer test-token"})
        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(allowed.json()["role"], "OWNER")
        self.assertEqual(allowed.json()["mode"], "PAPER")
        self.assertFalse(allowed.json()["personal_account"])
        verify.assert_called_once()

    def test_logout_revokes_session(self):
        with patch.object(postgres_api, "connect") as connect, \
             patch.object(postgres_identity, "revoke_session") as revoke:
            connection = MagicMock()
            connect.return_value.__enter__.return_value = connection
            response = self.client.post("/api/identity/logout",
                                        headers={"Authorization": "Bearer test-token"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["revoked"])
        revoke.assert_called_once_with(connection, "Bearer test-token")

    def test_database_outage_during_login_is_sanitized(self):
        with patch.object(postgres_api, "connect",
                          side_effect=RuntimeError("password=DO_NOT_EXPOSE")):
            response = self.client.post("/api/identity/login",
                                        json={"username": "owner123",
                                              "password": "example-password"})
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("DO_NOT_EXPOSE", response.text)
        self.assertEqual(response.json()["detail"], "Authentication service unavailable")

    def test_database_outage_during_owner_verification_is_sanitized(self):
        with patch.object(postgres_api, "connect",
                          side_effect=RuntimeError("password=DO_NOT_EXPOSE")):
            response = self.client.get("/api/identity/me/paper-account",
                                       headers={"Authorization": "Bearer test-token"})
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("DO_NOT_EXPOSE", response.text)
        self.assertEqual(response.json()["detail"], "Authentication service unavailable")


if __name__ == "__main__":
    unittest.main()
