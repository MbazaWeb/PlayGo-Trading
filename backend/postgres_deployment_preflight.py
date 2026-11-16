"""Phase 7G.1 deployment configuration preflight (read-only).

Checks the PostgreSQL API's deployment assumptions without connecting to a
database, changing trading state, or printing secrets. Exit 1 on unsafe config.
Run: python postgres_deployment_preflight.py
"""
import os
from pathlib import Path


def validate(env=None):
    env = os.environ if env is None else env
    findings = []
    deployment = env.get("PLAYGO_ENV", "").strip().lower()
    if deployment not in ("local", "development", "staging", "production"):
        findings.append("PLAYGO_ENV must explicitly identify the environment")
    if deployment == "production" and env.get("PLAYGO_OWNER_BOOTSTRAP_SECRET"):
        findings.append("Remove owner bootstrap secret from production environment")
    if not env.get("DATABASE_URL", "").strip():
        findings.append("DATABASE_URL is missing")
    else:
        from psycopg.conninfo import conninfo_to_dict
        try:
            params = conninfo_to_dict(env["DATABASE_URL"])
            if not params.get("dbname") or not (params.get("host") or params.get("hostaddr")):
                findings.append("DATABASE_URL requires an explicit database and host")
        except (ValueError, Exception) as exc:
            # Never print connection details or parsing exceptions.
            findings.append("DATABASE_URL is not a valid PostgreSQL connection string")
    origins = [x.strip() for x in env.get("CORS_ORIGINS", "").split(",") if x.strip()]
    if not origins:
        findings.append("CORS_ORIGINS must be explicitly configured")
    if "*" in origins or any(x == "null" for x in origins):
        findings.append("Wildcard or null CORS origin is forbidden")
    if deployment == "production" and any(not x.startswith("https://") for x in origins):
        findings.append("Production CORS origins must use HTTPS")
    if env.get("PLAYGO_SHARED_MONITOR_PATH"):
        path = Path(env["PLAYGO_SHARED_MONITOR_PATH"]).expanduser()
        if not path.is_absolute():
            findings.append("Shared monitor path must be absolute")
        elif not path.parent.is_dir():
            findings.append("Shared monitor directory must already exist")
    if env.get("PLAYGO_INCIDENT_SPOOL_PATH"):
        path = Path(env["PLAYGO_INCIDENT_SPOOL_PATH"]).expanduser()
        if not path.is_absolute():
            findings.append("Incident spool path must be absolute")
        elif not path.parent.is_dir():
            findings.append("Incident spool directory must already exist")
    if deployment == "production" and not env.get("PLAYGO_INCIDENT_SPOOL_PATH"):
        findings.append("Production incident spool persistence must be configured")
    if deployment == "production" and not env.get("PLAYGO_SHARED_MONITOR_PATH"):
        findings.append("Production shared monitor persistence must be configured")
    return findings


def main():
    findings = validate()
    if findings:
        print("FAIL: PlayGo deployment preflight")
        for item in findings:
            print("- " + item)
        return 1
    print("PASS: PlayGo deployment configuration preflight")
    print("PAPER ONLY; execution DISABLED; no database connection attempted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
