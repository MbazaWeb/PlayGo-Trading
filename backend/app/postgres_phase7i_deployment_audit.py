"""Phase 7I.1 stricter deployment configuration audit (offline, read-only).

Does not connect to PostgreSQL, inspect secret values, or certify production.
"""
import os
from pathlib import Path
from urllib.parse import urlsplit

from psycopg.conninfo import conninfo_to_dict
from app import postgres_deployment_preflight as base


def validate(env=None):
    env = os.environ if env is None else env
    findings = base.validate(env)
    deployment = env.get("PLAYGO_ENV", "").strip().lower()
    if deployment not in ("staging", "production"):
        findings.append("Deployment audit requires PLAYGO_ENV=staging or production")
    dsn = env.get("DATABASE_URL", "")
    if dsn:
        try:
            params = conninfo_to_dict(dsn)
            host = params.get("host", "").strip().lower()
            hostaddr = params.get("hostaddr", "").strip().lower()
            if deployment == "production" and (host in ("localhost", "127.0.0.1", "::1")
                                                or hostaddr in ("127.0.0.1", "::1")):
                findings.append("Production database must not target loopback")
            if deployment == "production" and params.get("sslmode") != "verify-full":
                findings.append("Production DATABASE_URL must specify sslmode=verify-full")
            if deployment == "production" and not host:
                findings.append("Production DATABASE_URL requires a hostname for TLS verification")
        except Exception:
            pass  # Base preflight reports sanitized DSN parsing errors.
    origins = [x.strip() for x in env.get("CORS_ORIGINS", "").split(",") if x.strip()]
    for origin in origins:
        try:
            parsed = urlsplit(origin)
            if (parsed.scheme not in ("http", "https") or not parsed.hostname
                    or parsed.username or parsed.password or parsed.path not in ("", "/")
                    or parsed.query or parsed.fragment or origin.endswith("/")):
                findings.append("CORS_ORIGINS entries must be bare scheme-and-host origins")
                break
            if deployment == "production" and parsed.scheme != "https":
                findings.append("Production CORS origin must use HTTPS")
                break
        except ValueError:
            findings.append("Invalid CORS origin")
            break
    paths = [env.get("PLAYGO_INCIDENT_SPOOL_PATH", ""),
             env.get("PLAYGO_SHARED_MONITOR_PATH", "")]
    if all(paths):
        try:
            if Path(paths[0]).expanduser().resolve() == Path(paths[1]).expanduser().resolve():
                findings.append("Incident spool and shared monitor must use separate files")
        except (OSError, ValueError):
            findings.append("Monitoring storage paths are invalid")
    if deployment == "production" and env.get("PLAYGO_OWNER_BOOTSTRAP_SECRET"):
        # Base preflight already blocks this; no need to reveal its value.
        pass
    return list(dict.fromkeys(findings))


def main():
    findings = validate()
    if findings:
        print("FAIL: Phase 7I.1 deployment configuration audit")
        for finding in findings:
            print("- " + finding)
        return 1
    print("PASS: Phase 7I.1 deployment configuration audit")
    print("LIMITATION: configuration only; infrastructure and actual TLS connectivity unverified")
    print("PAPER ONLY; execution DISABLED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
