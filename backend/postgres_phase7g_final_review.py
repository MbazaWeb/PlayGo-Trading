"""Phase 7G.4 final deployment review, offline and read-only.

Checks source-level safety invariants and migration ordering. This is NOT a
production deployment certification or a substitute for integration tests.
"""
from pathlib import Path
import re

import postgres_deployment_preflight as preflight

ROOT = Path(__file__).resolve().parent


def review(root=ROOT):
    findings = []
    def read(relative):
        path = root / relative
        if not path.is_file():
            findings.append("Missing required source: " + relative)
            return ""
        return path.read_text(encoding="utf-8")

    api = read("postgres_api.py")
    readiness = read("postgres_readiness.py")
    foundation = read("sql/supabase_foundation.sql").lower()
    identity = read("sql/supabase_owner_identity.sql").lower()

    # These are conservative source checks, not a Python security proof.
    if not re.search(r'@app\.get\(["\']/api/health["\']\)', api):
        findings.append("Missing liveness route")
    if not re.search(r'@app\.get\(["\']/api/ready["\']\)', api):
        findings.append("Missing readiness route")
    if "postgres_readiness.check(conn)" not in api:
        findings.append("Readiness route is not wired to schema checks")
    if "postgres_readiness.unavailable()" not in api:
        findings.append("Readiness failure response is not wired")
    if "HTTPException(503" not in api:
        findings.append("Readiness fail-closed HTTP 503 not found")
    if "SELECT 1" not in readiness or "SELECT to_regclass(%s)" not in readiness:
        findings.append("Readiness database/schema probes missing")
    for table in ("playgo_private.owners", "playgo_private.documents",
                  "playgo_private.owner_sessions"):
        if table == "playgo_private.owners":
            source = identity
        else:
            source = foundation
        if "create table if not exists " + table not in source:
            findings.append("Required migration table missing: " + table)
    if "on playgo_private.owner_sessions(owner_id)" not in identity:
        findings.append("Owner identity migration dependency changed")
    if "revoke all on schema playgo_private from public, anon, authenticated" in foundation:
        # Not a failure: explicit operator notice for local standalone PostgreSQL.
        notes = ["Supabase migration uses anon/authenticated roles; standalone PostgreSQL needs the documented local-compatible role adjustment"]
    else:
        notes = []
    for key in ('"PAPER"', '"DISABLED"', '"automation_enabled": False',
                '"eligible": False'):
        if key not in readiness:
            findings.append("Readiness PAPER-only invariant missing: " + key)
    return findings, notes


def main():
    findings, notes = review()
    if findings:
        print("FAIL: Phase 7G.4 offline source review")
        for finding in findings:
            print("- " + finding)
        return 1
    print("PASS: Phase 7G.4 offline source review")
    for note in notes:
        print("NOTE: " + note)
    print("LIMITATION: deployment credentials, production networking, and runtime availability not verified")
    print("PAPER ONLY; execution DISABLED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
