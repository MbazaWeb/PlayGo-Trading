"""Phase 7G.2 PostgreSQL readiness probes; never enable trading.

Checks connectivity and required schema. Does not mutate the database.
"""
import psycopg

REQUIRED_TABLES = ("playgo_private.owners", "playgo_private.documents")


def check(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT 1")
        row = cur.fetchone()
        if row is None or row[0] != 1:
            raise RuntimeError("Database readiness probe failed")
        for table in REQUIRED_TABLES:
            cur.execute("SELECT to_regclass(%s)", (table,))
            row = cur.fetchone()
            if row is None or row[0] is None:
                raise RuntimeError("Required private schema unavailable")
    return {"ready": True, "mode": "PAPER", "execution": "DISABLED",
            "automation_enabled": False, "eligible": False,
            "database": "CONNECTED"}


def unavailable():
    return {"ready": False, "mode": "PAPER", "execution": "DISABLED",
            "automation_enabled": False, "eligible": False,
            "database": "UNAVAILABLE"}
