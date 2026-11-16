"""Phase 7F.2: explicit, bounded local SQLite incident spool and PG replay.

The spool is opt-in and must reside on persistent, private storage. Never
stores DSNs, passwords, SQL, exception text, or user data. No background job.
"""
import json
import os
from pathlib import Path
import sqlite3
import time
from uuid import uuid4

COLLECTION = "paper_operational_incidents"
KINDS = {"OUTAGE", "RECOVERY"}
CATEGORIES = {"DATABASE_ERROR", "STATE_ERROR"}
MAX_PENDING = 1000


def _path():
    raw = os.getenv("PLAYGO_INCIDENT_SPOOL_PATH", "")
    if not raw:
        raise RuntimeError("PLAYGO_INCIDENT_SPOOL_PATH not configured")
    path = Path(raw).expanduser().resolve()
    if path.is_dir():
        raise RuntimeError("Spool path must be a file")
    if not path.parent.is_dir():
        raise RuntimeError("Spool directory does not exist")
    return path


def _open():
    path = _path()
    # The operator must provision a private directory. Restrict file perms
    # at creation on POSIX; Windows ACLs remain operator responsibility.
    if not path.exists():
        fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
        os.close(fd)
    conn = sqlite3.connect(str(path), timeout=5)
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""CREATE TABLE IF NOT EXISTS incidents (
        incident_id TEXT PRIMARY KEY, kind TEXT NOT NULL,
        category TEXT NOT NULL, occurred_at INTEGER NOT NULL,
        delivered INTEGER NOT NULL DEFAULT 0)""")
    return conn


def enqueue(kind, category="DATABASE_ERROR"):
    if kind not in KINDS or category not in CATEGORIES:
        raise ValueError("Invalid incident kind or category")
    with _open() as conn:
        pending = conn.execute(
            "SELECT count(*) FROM incidents WHERE delivered=0"
        ).fetchone()[0]
        if pending >= MAX_PENDING:
            raise RuntimeError("Incident spool capacity reached")
        incident_id = str(uuid4())
        conn.execute(
            "INSERT INTO incidents (incident_id,kind,category,occurred_at) "
            "VALUES (?,?,?,?)",
            (incident_id, kind, category, int(time.time())),
        )
    return incident_id


def pending_count():
    with _open() as conn:
        return conn.execute(
            "SELECT count(*) FROM incidents WHERE delivered=0"
        ).fetchone()[0]


def flush(pg_conn, limit=100):
    """Idempotent PG writes. Mark local delivery only after PG commit.

    A crash between commit and local marking is safe to replay because
    (collection_name, document_id) is unique in PostgreSQL.
    """
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("Invalid flush limit")
    with _open() as local:
        rows = local.execute(
            "SELECT incident_id,kind,category,occurred_at FROM incidents "
            "WHERE delivered=0 ORDER BY occurred_at,incident_id LIMIT ?",
            (limit,),
        ).fetchall()
        if not rows:
            return 0
        with pg_conn.transaction():
            with pg_conn.cursor() as cur:
                for incident_id, kind, category, occurred_at in rows:
                    body = {
                        "incident_id": incident_id, "kind": kind,
                        "category": category, "occurred_at": occurred_at,
                        "mode": "PAPER", "execution": "DISABLED",
                    }
                    cur.execute(
                        """INSERT INTO playgo_private.documents
                        (collection_name, document_id, body, revision)
                        VALUES (%s,%s,%s::jsonb,0)
                        ON CONFLICT (collection_name,document_id) DO NOTHING""",
                        (COLLECTION, incident_id, json.dumps(body)),
                    )
        local.executemany(
            "UPDATE incidents SET delivered=1 WHERE incident_id=?",
            [(row[0],) for row in rows],
        )
    return len(rows)


def list_recent(pg_conn, limit=25):
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("Invalid limit")
    with pg_conn.cursor() as cur:
        cur.execute(
            """SELECT body FROM playgo_private.documents
            WHERE collection_name=%s
            ORDER BY updated_at DESC,document_id DESC LIMIT %s""",
            (COLLECTION, limit),
        )
        rows = cur.fetchall()
    return {
        "mode": "PAPER", "execution": "DISABLED",
        "incidents": [v if isinstance(v, dict) else json.loads(v)
                      for (v,) in rows],
    }
