"""Owner authorization boundary tests; no MongoDB or network required."""
import unittest
from company import COMPANY_ID, CompanyAccessError
from identity import IdentityError, login, register
from owner_access import authorize_owner, permission_for


class Users:
    def __init__(self):
        self.rows = {}
    def find_one(self, query):
        for row in self.rows.values():
            if all(row.get(k) == v for k, v in query.items()):
                return dict(row)
        return None
    def insert_one(self, row):
        self.rows[row["_id"]] = dict(row)


class Sessions:
    def __init__(self):
        self.rows = {}
    def insert_one(self, row):
        self.rows[row["_id"]] = dict(row)
    def find_one(self, query):
        row = self.rows.get(query["_id"])
        if row and row["expires_at"] > query["expires_at"]["$gt"]:
            return dict(row)
        return None


class OwnerAccessTests(unittest.TestCase):
    def setUp(self):
        self.users = Users()
        self.sessions = Sessions()
        self.owner = register(self.users, username="owner", password="long-secret-password")
        self.token = "Bearer " + login(self.users, self.sessions,
                                      username="owner",
                                      password="long-secret-password")["access_token"]

    def authorize(self, path, method="GET", token=None):
        return authorize_owner(path=path, method=method,
                               authorization=self.token if token is None else token,
                               users=self.users, sessions=self.sessions)

    def test_owner_can_access_trading_and_accounting(self):
        for path, method in (
            ("/api/status", "GET"), ("/api/start", "POST"),
            ("/api/auto-cycle", "POST"), ("/api/orders", "POST"),
            ("/api/accounting/journals", "POST"),
            ("/api/accounting/reconciliation", "GET"),
            ("/api/identity/logout", "POST"),
        ):
            self.assertEqual(self.authorize(path, method)["company_id"], COMPANY_ID)

    def test_no_token_rejected(self):
        for path in ("/api/status", "/api/orders", "/api/accounting/journals"):
            with self.assertRaises(IdentityError):
                self.authorize(path, "GET", "")

    def test_wrong_company_or_disabled_owner_rejected(self):
        row = self.users.rows[self.owner["user_id"]]
        row["company_id"] = "OTHER"
        with self.assertRaises(CompanyAccessError):
            self.authorize("/api/status")
        row["company_id"] = COMPANY_ID
        row["disabled"] = True
        with self.assertRaises(CompanyAccessError):
            self.authorize("/api/status")

    def test_nonowner_role_rejected(self):
        self.users.rows[self.owner["user_id"]]["role"] = "TRADER"
        with self.assertRaises(CompanyAccessError):
            self.authorize("/api/start", "POST")

    def test_auth_routes_are_public_only_after_network_gate(self):
        self.assertIsNone(permission_for("/api/identity/login", "POST"))
        self.assertIsNone(permission_for("/api/health", "GET"))
        self.assertEqual(permission_for("/api/positions/abc/close", "POST"), "trade")
        self.assertEqual(permission_for("/api/accounting/journals", "POST"), "accounting")


if __name__ == "__main__":
    unittest.main()
