"""Phase 7E.2: process-local, bounded operational outage telemetry.

No credentials, DSNs, SQL or exception strings are logged. Metrics reset on
process restart and are not shared between workers; not a durable audit log.
"""
import logging
from threading import Lock
from time import time

logger = logging.getLogger("playgo.operational")
_lock = Lock()
_state = {
    "consecutive_failures": 0,
    "last_failure_at": None,
    "last_recovery_at": None,
    "last_failure_category": None,
}


def record_failure(category="DATABASE_ERROR"):
    if category not in ("DATABASE_ERROR", "STATE_ERROR"):
        category = "DATABASE_ERROR"
    with _lock:
        _state["consecutive_failures"] += 1
        _state["last_failure_at"] = int(time())
        _state["last_failure_category"] = category
        count = _state["consecutive_failures"]
    logger.error(
        "playgo_operational_failure category=%s consecutive_failures=%d",
        category, count,
    )


def record_success():
    with _lock:
        previous = _state["consecutive_failures"]
        _state["consecutive_failures"] = 0
        if previous:
            _state["last_recovery_at"] = int(time())
    if previous:
        logger.info("playgo_operational_recovered prior_failures=%d", previous)


def snapshot():
    with _lock:
        return dict(_state)


def diagnostics():
    """Sanitized, read-only Phase 7F.1 status; never implies execution readiness.

    This is process-local telemetry, not durable audit or multi-worker health.
    """
    state = snapshot()
    failures = state["consecutive_failures"]
    return {
        "phase": "7F.1",
        "mode": "PAPER",
        "execution": "DISABLED",
        "automation_enabled": False,
        "eligible": False,
        "monitor_scope": "PROCESS_LOCAL",
        "health": "DEGRADED" if failures else "NO_RECORDED_FAILURES",
        "consecutive_failures": failures,
        "last_failure_at": state["last_failure_at"],
        "last_recovery_at": state["last_recovery_at"],
        "last_failure_category": state["last_failure_category"],
    }
