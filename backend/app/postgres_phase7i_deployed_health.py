"""Phase 7I.3 deployed API health verification (read-only).

Explicit HTTPS origin required. Only GET /api/health and /api/ready.
Never sends credentials, mutates data, or enables trading.
"""
import argparse
import json
import ssl
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


def validate_origin(origin):
    parsed = urlsplit(origin)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username
            or parsed.password or parsed.path not in ("", "/") or parsed.query
            or parsed.fragment or origin.endswith("/")):
        raise ValueError("A bare HTTPS API origin is required")
    return origin


def fetch(origin, path, timeout=8):
    request = Request(origin + path, method="GET",
                      headers={"Accept": "application/json"})
    try:
        with urlopen(request, timeout=timeout, context=ssl.create_default_context()) as response:
            return response.status, json.loads(response.read(16384))
    except HTTPError as exc:
        return exc.code, json.loads(exc.read(16384))


def verify(origin, get=fetch):
    validate_origin(origin)
    findings = []
    try:
        health_code, health = get(origin, "/api/health")
        if health_code != 200 or health.get("ok") is not True:
            findings.append("Liveness endpoint failed")
        if (health.get("mode") != "PAPER" or health.get("execution") != "DISABLED"
                or health.get("eligible") is not False
                or health.get("automation_enabled") is not False):
            findings.append("Liveness PAPER-only safety invariant failed")
    except (URLError, TimeoutError, OSError, ValueError, TypeError, json.JSONDecodeError):
        findings.append("Liveness endpoint unavailable or invalid")
    try:
        ready_code, ready = get(origin, "/api/ready")
        if ready_code == 200:
            if (ready.get("ready") is not True or ready.get("database") != "CONNECTED"):
                findings.append("Readiness success payload invalid")
        elif ready_code == 503:
            detail = ready.get("detail", {})
            if (not isinstance(detail, dict) or detail.get("ready") is not False
                    or detail.get("database") != "UNAVAILABLE"):
                findings.append("Readiness outage payload invalid")
            else:
                findings.append("Deployment database readiness unavailable (HTTP 503)")
        else:
            findings.append("Unexpected readiness HTTP status")
        payload = ready.get("detail", {}) if ready_code == 503 else ready
        if (not isinstance(payload, dict) or payload.get("mode") != "PAPER"
                or payload.get("execution") != "DISABLED"
                or payload.get("eligible") is not False
                or payload.get("automation_enabled") is not False):
            findings.append("Readiness PAPER-only safety invariant failed")
    except (URLError, TimeoutError, OSError, ValueError, TypeError, json.JSONDecodeError):
        findings.append("Readiness endpoint unavailable or invalid")
    return findings


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--origin", required=True, help="Bare HTTPS API origin (not frontend URL)")
    args = parser.parse_args(argv)
    try:
        findings = verify(args.origin)
    except ValueError:
        print("FAIL: invalid HTTPS API origin")
        return 1
    if findings:
        print("FAIL: Phase 7I.3 deployed health verification")
        for finding in findings:
            print("- " + finding)
        return 1
    print("PASS: Phase 7I.3 deployed API health and readiness")
    print("PAPER ONLY; execution DISABLED; no credentials sent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
