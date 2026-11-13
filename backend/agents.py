"""Phase 2: deterministic, paper-only strategy evaluation.

Explicitly not a live forex feed or AI model. Runs via POST /api/auto-cycle
or the optional backend/worker.py process, never in a web browser.
"""
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


def diagnostics(state: dict[str, Any]) -> list[dict[str, Any]]:
    """Read-only signal telemetry; HOLD is not an executable order."""
    rows = []
    for pair in PAIRS:
        prices = state.get("history", {}).get(pair, [])
        quote = state["quotes"][pair]
        spread = round((quote["ask"] - quote["bid"]) / pip_size(pair), 2)
        enough = len(prices) >= 23
        fast = round(ema(prices, 9), 6) if len(prices) >= 9 else None
        slow = round(ema(prices, 21), 6) if len(prices) >= 21 else None
        crossed = signal(prices) if enough else None
        allowed = spread <= MAX_SPREAD_PIPS[pair]
        rows.append({
            "pair": pair, "signal": crossed if allowed and crossed else "HOLD",
            "ema_fast": fast, "ema_slow": slow, "spread_pips": spread,
            "observations": len(prices), "required_observations": 23,
            "ready": enough, "spread_acceptable": allowed,
            "reason": ("WARMING_UP" if not enough else
                       "SPREAD_TOO_WIDE" if not allowed else
                       "CROSSOVER" if crossed else "NO_CROSSOVER"),
        })
    return rows


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
            "source": f"{state.get('feed_type', 'SYNTHETIC')}_EMA_9_21", "observation_count": len(prices)}


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
            core.log("Strategy", f'{pair} {proposal["side"]}: EMA(9/21) sampled-price crossover')
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
    return {"auto_worker_enabled": False,
            "worker_note": "Start backend/worker.py separately; process status is not tracked",
            "configured_feed": os.getenv("FOREX_FEED", "synthetic").upper(),
            "strategy": "EMA_9_21_CROSS", "execution": "PAPER"}
