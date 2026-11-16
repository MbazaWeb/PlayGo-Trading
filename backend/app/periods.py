"""UTC time-window analytics for completed PAPER trades.

Uses recorded close timestamps, never projects guaranteed income.
Legacy trades without closed_at are excluded from windowed P&L.
"""
from datetime import datetime, timedelta, timezone
from typing import Any

WINDOWS = ("minute", "hour", "day", "week", "month")


def utc_time(value: str) -> datetime:
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Trade close time must include a timezone")
    return result.astimezone(timezone.utc)


def window_start(window: str, now: datetime) -> datetime:
    if window not in WINDOWS:
        raise ValueError("Unsupported time window")
    now = now.astimezone(timezone.utc)
    if window == "minute":
        return now.replace(second=0, microsecond=0)
    if window == "hour":
        return now.replace(minute=0, second=0, microsecond=0)
    if window == "day":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if window == "week":
        day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return day - timedelta(days=day.weekday())
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def summarize(trades: list[dict[str, Any]], now: datetime | None = None) -> dict[str, Any]:
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    results = {}
    legacy_count = 0
    eligible = []
    for trade in trades:
        raw = trade.get("closed_at")
        if not raw:
            legacy_count += 1
            continue
        try:
            closed = utc_time(raw)
        except (ValueError, TypeError):
            legacy_count += 1
            continue
        if closed <= current:
            eligible.append((closed, float(trade.get("pnl", 0))))
    for window in WINDOWS:
        start = window_start(window, current)
        pnl = [amount for closed, amount in eligible if start <= closed <= current]
        results[window] = {
            "start_utc": start.isoformat(),
            "end_utc": current.isoformat(),
            "closed_trades": len(pnl),
            "wins": sum(v > 0 for v in pnl),
            "losses": sum(v < 0 for v in pnl),
            "realized_pnl_usd": round(sum(pnl), 2),
            "profitable": sum(pnl) > 0,
        }
    return {
        "mode": "PAPER",
        "currency": "USD",
        "windows": results,
        "legacy_trades_without_valid_close_time": legacy_count,
        "disclaimer": "Historical realized virtual P&L only; not income or a forecast.",
    }
