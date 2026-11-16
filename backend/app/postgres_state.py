"""Paper-only PostgreSQL state service, independent of legacy MongoDB.

The database row is authoritative; do not cache writable state in a
serverless worker. Writes require the revision the owner last read.
"""
from datetime import datetime, timezone
from copy import deepcopy
import json

from app import postgres_ledger


PAIRS = {"EURUSD": (1.085, 0.0001, 0.00012),
         "GBPUSD": (1.265, 0.0001, 0.00018),
         "USDJPY": (151.0, 0.01, 0.018)}


def initial_state():
    quotes = {}
    for pair, (mid, pip, spread) in PAIRS.items():
        precision = 5 if pip < 0.01 else 3
        quotes[pair] = {"bid": round(mid - spread / 2, precision),
                        "ask": round(mid + spread / 2, precision),
                        "pip": pip, "spread": spread}
    return {
        "balance": 10000.0, "starting_balance": 10000.0,
        "day_start_balance": 10000.0,
        "day_start_date": datetime.now(timezone.utc).date().isoformat(),
        "positions": [], "history": {}, "signals": [], "trades": [],
        "logs": [], "paused": True, "quotes": quotes,
        "feed_type": "SYNTHETIC", "ticks": 0, "last_cycle_at": None,
        "loss_streak": 0, "risk_lock_reason": None,
        "equity_history": [], "revision": 0,
    }


def load(conn):
    """Read the persisted state without creating or overwriting records."""
    with conn.cursor() as cur:
        cur.execute(
            """select body, revision from playgo_private.documents
               where collection_name=%s and document_id=%s""",
            (postgres_ledger.COLLECTION, postgres_ledger.STATE_ID))
        row = cur.fetchone()
    if row is None:
        raise RuntimeError("Paper trading state has not been initialized")
    state = row[0] if isinstance(row[0], dict) else json.loads(row[0])
    state = deepcopy(state)
    state["revision"] = int(row[1])
    return state


def initialize(conn):
    """First start only: create a paused synthetic account, never reset it."""
    return postgres_ledger.load_or_initialize(conn, initial_state())


def commit(conn, previous, proposed):
    """Validate invariants and perform a compare-and-swap database commit.

    This method is for trusted internal engine code only, never for accepting
    arbitrary state from an external HTTP request.
    """
    if type(previous) is not dict or type(proposed) is not dict:
        raise ValueError("Invalid state")
    if type(previous.get("revision")) is not int:
        raise ValueError("Missing expected revision")
    if proposed.get("feed_type") != "SYNTHETIC":
        raise ValueError("Only synthetic paper quotes are supported")
    if previous.get("automation_emergency_stop") is True:
        if proposed.get("automation_emergency_stop") is not True:
            raise ValueError("Emergency stop cannot be cleared")
        if proposed.get("paused") is not True:
            raise ValueError("Emergency-stopped PAPER engine must remain paused")
    if proposed.get("starting_balance") != previous.get("starting_balance"):
        raise ValueError("Starting paper balance is immutable")
    if not isinstance(proposed.get("trades"), list):
        raise ValueError("Invalid closed trade history")
    prior = previous.get("trades", [])
    if not isinstance(prior, list) or proposed["trades"][:len(prior)] != prior:
        raise ValueError("Closed trade history must be append-only")
    if type(proposed.get("revision")) is not int or proposed["revision"] != previous["revision"]:
        raise ValueError("Expected revision mismatch")
    return postgres_ledger.commit_state(conn, previous, proposed)


def set_paused(conn, *, expected_revision: int, paused: bool):
    """Owner control with optimistic concurrency; no implicit engine execution."""
    if type(expected_revision) is not int or expected_revision < 0:
        raise ValueError("Invalid expected revision")
    if type(paused) is not bool:
        raise ValueError("Invalid paused flag")
    previous = load(conn)
    if previous["revision"] != expected_revision:
        raise postgres_ledger.StaleStateError("Paper state changed; reload before retrying")
    if not paused and previous.get("automation_emergency_stop") is True:
        raise ValueError("Emergency stop is engaged; unpausing is forbidden")
    if previous["paused"] == paused:
        return previous
    proposed = deepcopy(previous)
    proposed["paused"] = paused
    # Unpausing must never override an existing risk lock.
    if not paused:
        if proposed.get("automation_emergency_stop", False) is not False:
            raise ValueError("Emergency stop is engaged; unpausing is forbidden")
        today = datetime.now(timezone.utc).date().isoformat()
        if proposed.get("day_start_date") != today:
            raise ValueError("New UTC session requires a risk reset before starting")
        if proposed.get("risk_lock_reason") or proposed.get("loss_streak", 0) >= 3:
            raise ValueError("Risk lock prevents starting paper trading")
        if proposed.get("balance", 0) <= proposed.get("day_start_balance", 0) * 0.98:
            raise ValueError("Daily drawdown limit prevents starting paper trading")
    proposed.setdefault("logs", []).insert(0, {
        "id": "control:" + str(expected_revision + 1),
        "time": datetime.now(timezone.utc).isoformat(),
        "agent": "Supervisor",
        "message": "Paper trading paused" if paused else "Paper trading enabled",
    })
    proposed["logs"] = proposed["logs"][:100]
    revision = commit(conn, previous, proposed)
    proposed["revision"] = revision
    return proposed
