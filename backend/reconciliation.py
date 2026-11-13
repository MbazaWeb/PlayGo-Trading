"""Read-only reconciliation of paper position and trade records.

Identifies discrepancies without mutating financial state.
"""
from collections import Counter
from typing import Any


def reconcile(positions: list[dict[str, Any]],
              trades: list[dict[str, Any]],
              balance: float, starting_balance: float) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    ids = [item.get("id") for item in positions + trades]
    duplicates = sorted(str(key) for key, count in Counter(ids).items() if key and count > 1)
    for key in duplicates:
        issues.append({"code": "DUPLICATE_ORDER_ID", "reference": key})
    for item in positions:
        if not item.get("id") or item.get("units", 0) <= 0:
            issues.append({"code": "INVALID_OPEN_POSITION", "reference": str(item.get("id"))})
    for trade in trades:
        if not trade.get("id") or "pnl" not in trade:
            issues.append({"code": "INCOMPLETE_CLOSED_TRADE", "reference": str(trade.get("id"))})
    try:
        realized = round(sum(float(t["pnl"]) for t in trades), 2)
        expected = round(float(starting_balance) + realized, 2)
        actual = round(float(balance), 2)
        difference = round(actual - expected, 2)
        if abs(difference) > 0.01:
            issues.append({"code": "BALANCE_MISMATCH", "reference": str(difference)})
    except (ValueError, TypeError, KeyError, OverflowError):
        expected, difference = None, None
        issues.append({"code": "INVALID_ACCOUNTING_VALUES", "reference": "balance_or_pnl"})
    return {
        "mode": "PAPER",
        "consistent": not issues,
        "open_positions": len(positions),
        "closed_trades": len(trades),
        "expected_balance_usd": expected,
        "balance_difference_usd": difference,
        "issues": issues,
        "note": "Diagnostic only. Not a substitute for an immutable audited ledger.",
    }
