"""API access policy tests; no database or external service required."""
import unittest
from access_policy import authorize

TOKEN = "a" * 40


class AccessPolicyTests(unittest.TestCase):
    def test_local_read_and_write(self):
        for method in ("GET", "POST"):
            self.assertTrue(authorize(path="/api/status", method=method,
                                      headers={}, peer="127.0.0.1",
                                      environment="local", configured_token="")[0])

    def test_remote_default_denied(self):
        ok, status, _ = authorize(path="/api/status", method="GET",
                                  headers={}, peer="198.51.100.1",
                                  environment="local", configured_token="")
        self.assertFalse(ok)
        self.assertEqual(status, 403)

    def test_remote_read_requires_token(self):
        args = dict(path="/api/status", method="GET", peer="198.51.100.1",
                    environment="local", configured_token=TOKEN)
        self.assertEqual(authorize(headers={}, **args)[1], 401)
        self.assertEqual(authorize(headers={"authorization": "Bearer wrong"}, **args)[1], 401)
        self.assertTrue(authorize(headers={"authorization": "Bearer " + TOKEN}, **args)[0])

    def test_remote_mutations_always_denied(self):
        ok, status, _ = authorize(path="/api/accounting/journals", method="POST",
                                  headers={"authorization": "Bearer " + TOKEN},
                                  peer="198.51.100.1", environment="local",
                                  configured_token=TOKEN)
        self.assertFalse(ok)
        self.assertEqual(status, 403)

    def test_nonlocal_environment_denies_everything(self):
        self.assertFalse(authorize(path="/api/status", method="GET",
                                   headers={"authorization": "Bearer " + TOKEN},
                                   peer="127.0.0.1", environment="production",
                                   configured_token=TOKEN)[0])

    def test_openapi_docs_are_private(self):
        self.assertFalse(authorize(path="/openapi.json", method="GET",
                                   headers={}, peer="198.51.100.1",
                                   environment="local", configured_token="")[0])

    def test_public_non_api_routes_unaffected(self):
        self.assertTrue(authorize(path="/", method="GET", headers={},
                                  peer="198.51.100.1", environment="production",
                                  configured_token="")[0])


if __name__ == "__main__":
    unittest.main()
