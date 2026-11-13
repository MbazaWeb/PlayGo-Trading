"""Phase 2: deterministic, synthetic-only autonomous paper trading.

Explicitly not a live forex feed or AI model. Runs via POST /api/auto-cycle
or an optional single backend worker (AUTO_WORKER=true), never in a web browser.
"""
from collections import deque
from datetime import datetime, timezone
from statistics import mean
from threading import RLock
from typing import Any
import os

PAIRS = ("EURUSD", "GBPUSD")
MAX_CANDLES = 120
MAX_SPREAD_PIPS = {"EURUSD": 2.0, "GBPUSD": 2.5}
_cycle_lock = RLock()


def pip_size(pair: str) -> float:
    return 0.0001 if pair.endswith("USD") else 0.01


def append_price(state: dict[str, Any], pair: str) -> None:
    q = state["quotes"][pair]
    mid = round((q["bid"] + q["ask"]) / 2, 6)
    state.setdefault("history", {}).setdefault(pair, []).append(mid)
    state["history"][pair] = state["history"][pair][-MAX_CANDLES:]


def ema(values: list[float], period: int) -> float:
    if len(values) < period:
        raise ValueError("Insufficient observations")
    k = 2 / (period + 1)
    value = mean(values[:period])
    for price in values[period:]:
        value += (price - value) * k
    return value


def signal(prices: list[float]) -> str | None:
    """Baseline EMA(9/21) crossing on sampled synthetic midpoints, not candles."""
    if len(prices) < 23:
        return None
    prior_fast, prior_slow = ema(prices[:-1], 9), ema(prices[:-1], 21)
    now_fast, now_slow = ema(prices, 9), ema(prices, 21)
    if prior_fast <= prior_slow and now_fast > now_slow:
        return "BUY"
    if prior_fast >= prior_slow and now_fast < now_slow:
        return "SELL"
    return None


def create_signal(state: dict[str, Any], pair: str) -> dict[str, Any] | None:
    q = state["quotes"][pair]
    spread_pips = (q["ask"] - q["bid"]) / pip_size(pair)
    if spread_pips > MAX_SPREAD_PIPS[pair]:
        return None
    prices = state.setdefault("history", {}).get(pair, [])
    side = signal(prices)
    if not side:
        return None
    return {"pair": pair, "side": side, "stop_pips": 20, "take_profit_pips": 40,
            "source": "SYNTHETIC_EMA_9_21", "observation_count": len(prices)}


def evaluate(state: dict[str, Any], pair: str) -> dict[str, Any] | None:
    """Scanner + Strategy. A caller must still pass every signal to the core risk engine."""
    append_price(state, pair)
    return create_signal(state, pair)


def tick_cycle(core: Any) -> dict[str, Any]:
    """Run one simulation and risk-approved order cycle.

    core must export tick, order, state, Order, log, persist_state, snapshot.
    Cycle must be called only by the authenticated/local control plane.
    """
    from copy import deepcopy
    with _cycle_lock:
        # Core tick persists market move and stop/target changes first.
        core.tick()
        if core.state["paused"]:
            return core.snapshot()
        for pair in PAIRS:
            previous = deepcopy(core.state)
            proposal = evaluate(core.state, pair)
            if proposal is None:
                core.persist_state(previous)  # preserve history even if no signal
                continue
            core.state.setdefault("signals", []).append({**proposal, "created_at": datetime.now(timezone.utc).isoformat()})
            core.state["signals"] = core.state["signals"][-100:]
            core.log("Strategy", f'{pair} {proposal["side"]}: EMA(9/21) synthetic crossover')
            core.persist_state(previous)
            try:
                core.order(core.Order(**{k: proposal[k] for k in ("pair", "side", "stop_pips", "take_profit_pips")}))
            except Exception as exc:
                # An invalid/unsafe signal must never disable risk checks.
                previous = deepcopy(core.state)
                core.log("Risk Checker", f'{pair} proposal rejected: {type(exc).__name__}')
                core.persist_state(previous)
        return core.snapshot()


def options() -> dict[str, Any]:
    return {"auto_worker_enabled": os.getenv("AUTO_WORKER", "false").lower() == "true",
            "feed": "SYNTHETIC", "strategy": "EMA_9_21_CROSS", "execution": "PAPER"}
