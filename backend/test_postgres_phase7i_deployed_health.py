"""Phase 7I.3 remote health verification with simulated HTTP responses."""
import unittest
import postgres_phase7i_deployed_health as probe

HEALTH = {"ok": True, "mode": "PAPER", "execution": "DISABLED",
          "eligible": False, "automation_enabled": False}
READY = {"ready": True, "database": "CONNECTED", "mode": "PAPER",
         "execution": "DISABLED", "eligible": False, "automation_enabled": False}
DOWN = {"ready": False, "database": "UNAVAILABLE", "mode": "PAPER",
        "execution": "DISABLED", "eligible": False, "automation_enabled": False}


class DeployedHealthTests(unittest.TestCase):
    def test_valid_deployment_passes(self):
        def get(origin, path):
            return (200, HEALTH if path == "/api/health" else READY)
        self.assertEqual(probe.verify("https://api.example.com", get), [])

    def test_database_outage_fails_acceptance(self):
        def get(origin, path):
            return (200, HEALTH) if path == "/api/health" else (503, {"detail": DOWN})
        self.assertTrue(any("unavailable" in f for f in probe.verify(
            "https://api.example.com", get)))

    def test_execution_enabled_rejected(self):
        def get(origin, path):
            return (200, HEALTH) if path == "/api/health" else (
                200, {**READY, "execution": "ENABLED"})
        self.assertTrue(any("safety invariant" in f for f in probe.verify(
            "https://api.example.com", get)))

    def test_non_https_origin_rejected(self):
        with self.assertRaises(ValueError):
            probe.verify("http://api.example.com", lambda *_: (200, HEALTH))

    def test_origin_with_path_or_credentials_rejected(self):
        for origin in ("https://api.example.com/api", "https://u:p@api.example.com"):
            with self.subTest(origin=origin), self.assertRaises(ValueError):
                probe.validate_origin(origin)

    def test_missing_health_fails(self):
        def get(origin, path):
            return (404, {}) if path == "/api/health" else (200, READY)
        self.assertTrue(probe.verify("https://api.example.com", get))


if __name__ == "__main__":
    unittest.main()
