"""Phase 7G.4 offline deployment review regression checks."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import postgres_phase7g_final_review as review


class FinalReviewTests(unittest.TestCase):
    def test_repository_source_invariants(self):
        findings, notes = review.review()
        self.assertEqual(findings, [])
        self.assertTrue(isinstance(notes, list))

    def test_missing_sources_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            findings, _ = review.review(Path(temp))
            self.assertTrue(any("Missing required source" in f for f in findings))

    def test_missing_execution_guard_detected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for relative in ("app/postgres_api.py", "app/postgres_readiness.py",
                             "sql/supabase_foundation.sql",
                             "sql/supabase_owner_identity.sql"):
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text((review.ROOT / relative).read_text(encoding="utf-8"),
                                  encoding="utf-8")
            ready = root / "app" / "postgres_readiness.py"
            ready.write_text(ready.read_text().replace('"eligible": False',
                                                       '"eligible": True'))
            findings, _ = review.review(root)
            self.assertTrue(any("PAPER-only invariant" in f for f in findings))

    def test_preflight_production_rejects_missing_persistence(self):
        config = {"PLAYGO_ENV": "production",
                  "DATABASE_URL": "postgresql://u:password@localhost:5432/demo",
                  "CORS_ORIGINS": "https://example.com"}
        findings = review.preflight.validate(config)
        self.assertTrue(any("spool" in f for f in findings))
        self.assertTrue(any("monitor" in f for f in findings))


if __name__ == "__main__":
    unittest.main()
