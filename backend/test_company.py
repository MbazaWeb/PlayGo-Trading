"""Company-owned account policy and migration safety tests."""
import unittest
from company import (COMPANY_ID, CompanyAccessError, require_permission,
                     migration_preview, staff_context)


class CompanyTests(unittest.TestCase):
    def test_staff_share_one_company(self):
        owner = {"_id": "a", "company_id": COMPANY_ID, "role": "OWNER"}
        trader = {"_id": "b", "company_id": COMPANY_ID, "role": "TRADER"}
        self.assertEqual(staff_context(owner)["company_id"], staff_context(trader)["company_id"])
        self.assertNotEqual(staff_context(owner)["staff_id"], staff_context(trader)["staff_id"])

    def test_permissions_enforced(self):
        trader = {"_id": "b", "company_id": COMPANY_ID, "role": "TRADER"}
        require_permission(trader, "trade")
        with self.assertRaises(CompanyAccessError):
            require_permission(trader, "accounting")
        with self.assertRaises(CompanyAccessError):
            require_permission(trader, "staff")

    def test_unassigned_or_disabled_staff_rejected(self):
        for user in ({"_id": "x", "role": "OWNER"},
                     {"_id": "x", "company_id": COMPANY_ID, "role": "OWNER", "disabled": True},
                     {"_id": "x", "company_id": "OTHER", "role": "OWNER"}):
            with self.assertRaises(CompanyAccessError):
                staff_context(user)

    def test_migration_preview_never_approves_automatic_cutover(self):
        preview = migration_preview({"revision": 7, "balance": 12000.0,
                                     "trades": [{"id": "x"}], "positions": []},
                                    {"revision": 2}, 2)
        self.assertFalse(preview["safe_to_auto_migrate"])
        self.assertEqual(preview["legacy_trade_count"], 1)
        self.assertEqual(preview["company_id"], COMPANY_ID)


if __name__ == "__main__":
    unittest.main()
