"""Phase 7H.4 offline deployment acceptance gate.

Runs verified local test suites and checks explicit deployment configuration.
Does not deploy, access production infrastructure, or enable execution.
"""
import argparse
import os
import subprocess
import sys

import postgres_deployment_preflight as preflight
import postgres_phase7g_final_review as review

SUITES = (
    "test_postgres_phase7g_preflight",
    "test_postgres_phase7g_readiness",
    "test_postgres_phase7g_final_review",
    "test_postgres_phase7h_lifespan",
    "test_postgres_phase7h_auth",
    "test_postgres_phase7h_persistence",
)


def assess(config=None, *, require_deployment=False):
    findings, notes = review.review()
    if require_deployment:
        findings.extend(preflight.validate(os.environ if config is None else config))
    return findings, notes


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--deployment", action="store_true",
                        help="Also validate actual deployment environment variables")
    args = parser.parse_args(argv)
    findings, notes = assess(require_deployment=args.deployment)
    if findings:
        print("FAIL: Phase 7H.4 acceptance configuration")
        for finding in findings:
            print("- " + finding)
        return 1
    for note in notes:
        print("NOTE: " + note)
    print("CHECK: running offline regression suites")
    result = subprocess.run([sys.executable, "-m", "unittest", "-v", *SUITES],
                            check=False)
    if result.returncode != 0:
        print("FAIL: Phase 7H.4 regression suites")
        return 1
    print("PASS: Phase 7H.4 offline acceptance gate")
    print("LIMITATION: live deployment, production database and infrastructure NOT verified")
    print("PAPER ONLY; execution DISABLED; no broker execution")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
