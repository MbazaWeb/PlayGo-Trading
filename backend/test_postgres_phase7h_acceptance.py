"""Phase 7H.4 acceptance gate tests; no production connections."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import postgres_phase7h_acceptance as acceptance


class AcceptanceTests(unittest.TestCase):
    def test_offline_review_does_not_require_secrets(self):
        findings, notes = acceptance.assess()
        self.assertEqual(findings, [])
        self.assertIsInstance(notes, list)

    def test_deployment_mode_rejects_missing_configuration(self):
        findings, _ = acceptance.assess({}, require_deployment=True)
        self.assertTrue(any("DATABASE_URL" in x for x in findings))
        self.assertTrue(any("PLAYGO_ENV" in x for x in findings))

    def test_deployment_mode_accepts_explicit_safe_configuration(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = {
                "PLAYGO_ENV": "production",
                "DATABASE_URL": "postgresql://owner:placeholder@db.example:5432/playgo",
                "CORS_ORIGINS": "https://example.com",
                "PLAYGO_INCIDENT_SPOOL_PATH": str(Path(tmp) / "incidents.sqlite"),
                "PLAYGO_SHARED_MONITOR_PATH": str(Path(tmp) / "monitor.sqlite"),
            }
            findings, _ = acceptance.assess(config, require_deployment=True)
            self.assertEqual(findings, [])

    def test_regression_suite_failure_blocks_acceptance(self):
        with patch.object(acceptance, "assess", return_value=([], [])), \
             patch.object(acceptance.subprocess, "run") as run:
            run.return_value.returncode = 1
            self.assertEqual(acceptance.main([]), 1)

    def test_regression_suite_success_reports_offline_only(self):
        with patch.object(acceptance, "assess", return_value=([], [])), \
             patch.object(acceptance.subprocess, "run") as run:
            run.return_value.returncode = 0
            self.assertEqual(acceptance.main([]), 0)
            self.assertIn("test_postgres_phase7h_auth", run.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
