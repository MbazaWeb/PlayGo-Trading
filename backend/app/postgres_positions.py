"""Phase 6A: pure PAPER position and risk calculations.

No order execution, database mutation, or broker connectivity. These
functions are intended for validation before transactional position cutover.
USD-quoted EURUSD/GBPUSD only; JPY conversion is intentionally unsupported.
"""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

SUPPORTED = frozenset(("EURUSD", "GBPUSD"))
MAX_POSITIONS = 5
MAX_EXPOSURE_USD = Decimal("20000")
MAX_POSITION_NOTIONAL_USD = Decimal("5000")
MAX_RISK_FRACTION = Decimal("0.01")
DAILY_DRAWDOWN = Decimal("0.02")


class RiskRejected(ValueError):
    pass


def number(value):
    if isinstance(value, bool):
        raise RiskRejected("Invalid numeric value")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise RiskRejected("Invalid numeric value") from exc
    if not result.is_finite():
        raise RiskRejected("Non-finite numeric value")
    return result


def validate_open(state, *, pair, side, units, entry_price, stop_loss):
    if pair not in SUPPORTED or side not in ("BUY", "SELL"):
        raise RiskRejected("Unsupported PAPER position")
    if type(units) is not int or not 1 <= units <= 100000:
        raise RiskRejected("Invalid position units")
    price, stop = number(entry_price), number(stop_loss)
    if price <= 0 or stop <= 0:
        raise RiskRejected("Prices must be positive")
    if side == "BUY" and stop >= price or side == "SELL" and stop <= price:
        raise RiskRejected("Stop loss must be on the losing side")
    if state.get("automation_emergency_stop") is True:
        raise RiskRejected("Emergency stop is engaged")
    if state.get("paused", True) or state.get("risk_lock_reason"):
        raise RiskRejected("Paper engine is paused or risk locked")
    if state.get("loss_streak", 0) >= 3:
        raise RiskRejected("Loss streak lock")
    balance = number(state.get("balance", 0))
    day_start = number(state.get("day_start_balance", 0))
    if balance <= 0 or day_start <= 0 or balance <= day_start * (1 - DAILY_DRAWDOWN):
        raise RiskRejected("Daily drawdown limit")
    positions = state.get("positions", [])
    if not isinstance(positions, list) or len(positions) >= MAX_POSITIONS:
        raise RiskRejected("Maximum open positions reached")
    notional = price * units
    exposure = notional
    for position in positions:
        if position.get("pair") not in SUPPORTED:
            raise RiskRejected("Unsupported existing exposure")
        exposure += number(position["entry_price"]) * int(position["units"])
    if notional > MAX_POSITION_NOTIONAL_USD or exposure > MAX_EXPOSURE_USD:
        raise RiskRejected("Exposure limit exceeded")
    at_risk = abs(price - stop) * units
    if at_risk > balance * MAX_RISK_FRACTION:
        raise RiskRejected("Risk per position exceeds 1% of paper balance")
    return {"pair": pair, "side": side, "units": units,
            "entry_price": str(price), "stop_loss": str(stop),
            "notional_usd": str(notional), "risk_usd": str(at_risk),
            "exposure_after_usd": str(exposure)}


def mark_to_market(position, quote):
    if position.get("pair") not in SUPPORTED:
        raise RiskRejected("Unsupported currency pair")
    side = position.get("side")
    if side not in ("BUY", "SELL"):
        raise RiskRejected("Invalid side")
    units = position.get("units")
    if type(units) is not int or units <= 0:
        raise RiskRejected("Invalid units")
    entry = number(position.get("entry_price"))
    exit_price = number(quote["bid"] if side == "BUY" else quote["ask"])
    if entry <= 0 or exit_price <= 0:
        raise RiskRejected("Invalid quote")
    pnl = (exit_price - entry) * units * (1 if side == "BUY" else -1)
    return {"exit_price": str(exit_price),
            "pnl_usd": str(pnl.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))}
