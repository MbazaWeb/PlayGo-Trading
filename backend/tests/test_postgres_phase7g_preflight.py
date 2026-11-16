"""Phase 7G.1 configuration safety regression tests."""
import tempfile
import unittest
from pathlib import Path

from app import postgres_deployment_preflight as preflight


class DeploymentPreflightTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.good = {
            "PLAYGO_ENV": "production",
            "DATABASE_URL": "postgresql://user:SECRET_VALUE@localhost:5432/playgo",
            "CORS_ORIGINS": "https://example.com",
            "PLAYGO_INCIDENT_SPOOL_PATH": str(root / "incidents.db"),
            "PLAYGO_SHARED_MONITOR_PATH": str(root / "monitor.db"),
        }

    def tearDown(self):
        self.tmp.cleanup()

    def test_valid_config_passes_without_database_connection(self):
        self.assertEqual(preflight.validate(self.good), [])

    def test_missing_persistent_paths_rejected(self):
        config = {k: v for k, v in self.good.items()
                  if k not in ("PLAYGO_INCIDENT_SPOOL_PATH", "PLAYGO_SHARED_MONITOR_PATH")}
        result = preflight.validate(config)
        self.assertEqual(len(result), 2)

    def test_insecure_cors_and_bootstrap_rejected(self):
        config = {**self.good, "CORS_ORIGINS": "http://example.com,*",
                  "PLAYGO_OWNER_BOOTSTRAP_SECRET": "not-for-production"}
        self.assertGreaterEqual(len(preflight.validate(config)), 3)

    def test_connection_string_never_leaked(self):
        config = {**self.good, "DATABASE_URL": "postgresql://:SECRET_VALUE"}
        output = "\n".join(preflight.validate(config))
        self.assertNotIn("SECRET_VALUE", output)

    def test_relative_shared_paths_rejected(self):
        config = {**self.good, "PLAYGO_SHARED_MONITOR_PATH": "monitor.db"}
        self.assertTrue(any("absolute" in x for x in preflight.validate(config)))


if __name__ == "__main__":
    unittest.main()
