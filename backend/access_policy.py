"""Fail-closed development API access policy.

A shared token is not user authentication or multi-tenancy. It only protects
private API access during development. Never embed it in browser bundles.
"""
import hmac
import os
from typing import Mapping


def authorize(*, path: str, method: str, headers: Mapping[str, str],
              peer: str, environment: str | None = None,
              configured_token: str | None = None) -> tuple[bool, int, str]:
    if not path.startswith("/api/"):
        return True, 200, "ok"
    env = (environment if environment is not None else os.getenv("PLAYGO_ENV", "local")).lower()
    token = configured_token if configured_token is not None else os.getenv("PLAYGO_DEV_API_TOKEN", "")
    local_peer = peer in ("127.0.0.1", "::1", "testclient")
    if env == "local" and local_peer:
        return True, 200, "ok"
    # Fail closed for all remote API traffic, including read endpoints.
    if env != "local" or len(token) < 32:
        return False, 403, "Remote API access disabled"
    supplied = headers.get("authorization", "")
    if not supplied.startswith("Bearer "):
        return False, 401, "Bearer token required"
    if not hmac.compare_digest(supplied[7:], token):
        return False, 401, "Invalid token"
    # Even with a token, shared-state mutations must stay localhost-only.
    if method.upper() not in ("GET", "HEAD", "OPTIONS"):
        return False, 403, "Remote writes disabled until account isolation exists"
    return True, 200, "ok"
