"""Single-request synthetic market cycle with durable PostgreSQL CAS.

This first engine migration only updates synthetic quotes, indicators and
risk telemetry. It deliberately does not open/close positions or execute
strategy signals until their accounting and risk transactions are integrated.
"""
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import random

import agents
import postgres_state

PAIRS = ("EURUSD", "GBPUSD")


class CycleCooldown(ValueError):
    pass


def simulate_cycle(previous: dict, *, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("Cycle timestamp must include timezone")
    if previous.get("feed_type") != "SYNTHETIC":
        raise ValueError("Only synthetic quotes are supported")
    last = previous.get("last_cycle_at")
    if last:
        elapsed = (now - datetime.fromisoformat(last)).total_seconds()
        if elapsed < 30:
            raise CycleCooldown("30-second cycle cooldown active")
    updated = deepcopy(previous)
    # Use per-cycle deterministic PRNG, never process-global mutable state.
    seed = sha256(f'{previous["revision"]}:{now.isoformat()}'.encode()).digest()
    rng = random.Random(int.from_bytes(seed, "big"))
    for pair, (base, pip, spread) in postgres_state.PAIRS.items():
        quote = updated["quotes"][pair]
        center = (quote["bid"] + quote["ask"]) / 2 + rng.gauss(0, pip * 2)
        precision = 5 if pip < 0.01 else 3
        quote["bid"] = round(center - spread / 2, precision)
        quote["ask"] = round(center + spread / 2, precision)
    updated["ticks"] += 1
    updated["last_cycle_at"] = now.isoformat()
    updated["day_start_date"] = updated.get("day_start_date") or now.date().isoformat()
    # Daily rollover must pause the engine before any new order processing.
    if updated["day_start_date"] != now.date().isoformat():
        updated["paused"] = True
        updated["day_start_date"] = now.date().isoformat()
        updated["day_start_balance"] = updated["balance"]
        updated["loss_streak"] = 0
        updated["risk_lock_reason"] = None
    updated["signals"] = updated.get("signals", [])[-100:]
    for pair in PAIRS:
        agents.append_price(updated, pair)
        diagnostics = agents.diagnostics(updated)
        row = next(x for x in diagnostics if x["pair"] == pair)
        if row["signal"] != "HOLD" and not updated["paused"]:
            updated["signals"].append({
                "pair": pair, "side": row["signal"], "source": "SYNTHETIC_EMA_9_21",
                "created_at": now.isoformat(), "status": "OBSERVATION_ONLY",
            })
    updated["signals"] = updated["signals"][-100:]
    updated.setdefault("logs", []).insert(0, {
        "id": f'cycle:{previous["revision"] + 1}',
        "time": now.isoformat(), "agent": "Scanner",
        "message": "Synthetic market cycle completed; order execution disabled",
    })
    updated["logs"] = updated["logs"][:100]
    return updated


def run_cycle(conn, *, expected_revision: int) -> dict:
    if type(expected_revision) is not int or expected_revision < 0:
        raise ValueError("Invalid expected revision")
    previous = postgres_state.load(conn)
    if previous["revision"] != expected_revision:
        raise postgres_state.postgres_ledger.StaleStateError("Paper account revision changed")
    proposed = simulate_cycle(previous)
    revision = postgres_state.commit(conn, previous, proposed)
    proposed["revision"] = revision
    return proposed
