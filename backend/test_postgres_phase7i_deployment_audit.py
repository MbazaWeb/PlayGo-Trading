"""Phase 7I.1 offline deployment configuration audit regression tests."""
import tempfile
import unittest
from pathlib import Path
import postgres_phase7i_deployment_audit as audit


class DeploymentAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.good = {
            "PLAYGO_ENV": "production",
            "DATABASE_URL": "postgresql://owner:placeholder@db.example.com:5432/playgo?sslmode=verify-full",
            "CORS_ORIGINS": "https://app.example.com",
            "PLAYGO_INCIDENT_SPOOL_PATH": str(root / "incidents.sqlite"),
            "PLAYGO_SHARED_MONITOR_PATH": str(root / "monitor.sqlite"),
        }

    def tearDown(self):
        self.tmp.cleanup()

    def test_safe_configuration_passes_offline(self):
        self.assertEqual(audit.validate(self.good), [])

    def test_production_requires_verified_tls(self):
        env = dict(self.good)
        env["DATABASE_URL"] = "postgresql://owner:placeholder@db.example.com/playgo?sslmode=require"
        self.assertTrue(any("verify-full" in f for f in audit.validate(env)))

    def test_loopback_database_rejected_in_production(self):
        env = dict(self.good)
        env["DATABASE_URL"] = "postgresql://owner:placeholder@127.0.0.1/playgo?sslmode=verify-full"
        self.assertTrue(any("loopback" in f for f in audit.validate(env)))

    def test_malformed_cors_origin_rejected(self):
        env = dict(self.good)
        env["CORS_ORIGINS"] = "https://app.example.com/path"
        self.assertTrue(any("bare" in f for f in audit.validate(env)))

    def test_storage_files_must_be_distinct(self):
        env = dict(self.good)
        env["PLAYGO_SHARED_MONITOR_PATH"] = env["PLAYGO_INCIDENT_SPOOL_PATH"]
        self.assertTrue(any("separate" in f for f in audit.validate(env)))

    def test_secret_not_printed_in_findings(self):
        env = dict(self.good)
        env["DATABASE_URL"] = "postgresql://:SUPER_SECRET_VALUE"
        self.assertNotIn("SUPER_SECRET_VALUE", "\n".join(audit.validate(env)))

    def test_local_mode_cannot_pass_deployment_audit(self):
        env = dict(self.good)
        env["PLAYGO_ENV"] = "local"
        self.assertTrue(any("staging or production" in f for f in audit.validate(env)))


if __name__ == "__main__":
    unittest.main()
