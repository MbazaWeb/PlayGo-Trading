"""Phase 7F.3: optional cross-process operational telemetry via local SQLite.

Requires all workers on the same host and the same persistent spool path.
Not a distributed health quorum. No database credentials or exception text.
"""
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from time import time

CATEGORIES = {"DATABASE_ERROR", "STATE_ERROR"}


def enabled():
    return bool(os.getenv("PLAYGO_SHARED_MONITOR_PATH"))


@contextmanager
def _connection():
    raw = os.getenv("PLAYGO_SHARED_MONITOR_PATH")
    if not raw:
        raise RuntimeError("Shared monitor path not configured")
    path = Path(raw).expanduser().resolve()
    if not path.parent.is_dir() or path.is_dir():
        raise RuntimeError("Shared monitor directory unavailable")
    if not path.exists():
        try:
            fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
        except FileExistsError:
            pass
        else:
            os.close(fd)
    conn = sqlite3.connect(str(path), timeout=5, isolation_level=None)
    try:
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("""CREATE TABLE IF NOT EXISTS monitor_state (
            id INTEGER PRIMARY KEY CHECK (id=1),
            consecutive_failures INTEGER NOT NULL DEFAULT 0,
            last_failure_at INTEGER,
            last_recovery_at INTEGER,
            last_failure_category TEXT)""")
        conn.execute("INSERT OR IGNORE INTO monitor_state (id) VALUES (1)")
        yield conn
    finally:
        conn.close()


def _read(conn):
    row = conn.execute(
        "SELECT consecutive_failures,last_failure_at,last_recovery_at,"
        "last_failure_category FROM monitor_state WHERE id=1"
    ).fetchone()
    return dict(zip(("consecutive_failures", "last_failure_at",
                     "last_recovery_at", "last_failure_category"), row))


def failure(category="DATABASE_ERROR"):
    if category not in CATEGORIES:
        category = "DATABASE_ERROR"
    with _connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute(
                "UPDATE monitor_state SET consecutive_failures=consecutive_failures+1,"
                "last_failure_at=?,last_failure_category=? WHERE id=1",
                (int(time()), category),
            )
            state = _read(conn)
            conn.commit()
            return state
        except BaseException:
            conn.rollback()
            raise


def success():
    with _connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            previous = _read(conn)["consecutive_failures"]
            conn.execute(
                "UPDATE monitor_state SET consecutive_failures=0,"
                "last_recovery_at=CASE WHEN ? > 0 THEN ? ELSE last_recovery_at END "
                "WHERE id=1", (previous, int(time())),
            )
            state = _read(conn)
            conn.commit()
            return state
        except BaseException:
            conn.rollback()
            raise


def snapshot():
    with _connection() as conn:
        return _read(conn)
