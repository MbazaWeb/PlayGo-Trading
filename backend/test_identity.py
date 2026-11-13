"""Identity and tenant isolation tests with minimal in-memory collections."""
import unittest
from copy import deepcopy
from pymongo.errors import DuplicateKeyError
from identity import (IdentityError, register, login, verify_session,
                      revoke_session, ensure_paper_account, account_for_session)


class Users:
    def __init__(self):
        self.rows = {}
    def insert_one(self, row):
        if any(u["username"] == row["username"] for u in self.rows.values()):
            raise DuplicateKeyError("duplicate")
        self.rows[row["_id"]] = deepcopy(row)
    def find_one(self, query):
        return next((deepcopy(u) for u in self.rows.values()
                     if all(u.get(k) == v for k, v in query.items())), None)


class Sessions:
    def __init__(self):
        self.rows = {}
    def insert_one(self, row):
        self.rows[row["_id"]] = deepcopy(row)
    def find_one(self, query):
        from datetime import datetime, timezone
        row = self.rows.get(query["_id"])
        return deepcopy(row) if row and row["expires_at"] > query["expires_at"]["$gt"] else None
    def delete_one(self, query):
        self.rows.pop(query["_id"], None)


class Accounts:
    def __init__(self):
        self.rows = {}
    def update_one(self, query, update, upsert):
        self.rows.setdefault(query["_id"], deepcopy({"_id": query["_id"], **update["$setOnInsert"]}))
    def find_one(self, query):
        row = self.rows.get(query["_id"])
        return deepcopy(row) if row and row["user_id"] == query["user_id"] else None


class IdentityTests(unittest.TestCase):
    def setUp(self):
        self.users, self.sessions, self.accounts = Users(), Sessions(), Accounts()

    def test_single_company_owner(self):
        from company import COMPANY_ID
        owner = register(self.users, username="alpha", password="strong-password-123")
        token = login(self.users, self.sessions, username="alpha",
                      password="strong-password-123")["access_token"]
        self.assertEqual(verify_session(self.sessions, "Bearer " + token), owner["user_id"])
        self.assertEqual(self.users.rows[owner["user_id"]]["company_id"], COMPANY_ID)
        self.assertEqual(self.users.rows[owner["user_id"]]["role"], "OWNER")
        with self.assertRaises(IdentityError):
            register(self.users, username="bravo", password="another-strong-password")

    def test_password_and_token_rejection(self):
        register(self.users, username="alpha", password="strong-password-123")
        with self.assertRaises(IdentityError):
            login(self.users, self.sessions, username="alpha", password="wrong-password")
        with self.assertRaises(IdentityError):
            verify_session(self.sessions, "Bearer invalid")

    def test_logout_revokes_session(self):
        register(self.users, username="alpha", password="strong-password-123")
        token = login(self.users, self.sessions, username="alpha", password="strong-password-123")["access_token"]
        self.assertTrue(verify_session(self.sessions, "Bearer " + token))
        revoke_session(self.sessions, "Bearer " + token)
        with self.assertRaises(IdentityError):
            verify_session(self.sessions, "Bearer " + token)

    def test_duplicate_registration_rejected(self):
        register(self.users, username="alpha", password="strong-password-123")
        with self.assertRaises(IdentityError):
            register(self.users, username="alpha", password="strong-password-456")

    def test_account_scope_rejects_bad_identity(self):
        with self.assertRaises(IdentityError):
            ensure_paper_account(self.accounts, "other-users-id")


if __name__ == "__main__":
    unittest.main()
