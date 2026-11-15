"""Read-only analytics from authoritative paper state and DEMO order records.

DEMO fills are NOT paper-account trades. Never infer P&L, win rate,
equity curve or drawdown from synthetic fills.
"""
import json
import postgres_state
from postgres_demo_orders import COLLECTION


def snapshot(conn):
    state = postgres_state.load(conn)
    with conn.cursor() as cur:
        cur.execute(
            """select body->>'status', body->'request'->>'pair',
                      count(*) from playgo_private.documents
               where collection_name=%s
               group by body->>'status', body->'request'->>'pair'""",
            (COLLECTION,))
        groups = cur.fetchall()
    by_status, by_pair = {}, {}
    total = 0
    for status, pair, count in groups:
        count = int(count)
        total += count
        by_status[status or "UNKNOWN"] = by_status.get(status or "UNKNOWN", 0) + count
        by_pair[pair or "UNKNOWN"] = by_pair.get(pair or "UNKNOWN", 0) + count
    trades = state.get("trades", [])
    positions = state.get("positions", [])
    if not isinstance(trades, list) or not isinstance(positions, list):
        raise ValueError("Invalid paper position or trade records")
    # No settlement-derived analytics until position lifecycle and accounting
    # are integrated. Balance and starting capital are factual snapshots only.
    return {
        "mode": "PAPER", "feed_type": state.get("feed_type"),
        "paper": {
            "balance": state["balance"],
            "starting_balance": state["starting_balance"],
            "revision": state["revision"],
            "observations": state.get("ticks", 0),
            "paused": state.get("paused", True),
            "risk_lock_reason": state.get("risk_lock_reason"),
            "open_positions": len(positions),
            "closed_trade_records": len(trades),
        },
        "demo_orders": {
            "total": total, "by_status": by_status, "by_pair": by_pair,
        },
        "performance": {
            "realized_pnl": None, "unrealized_pnl": None,
            "win_rate": None, "max_drawdown": None,
            "equity_curve": None,
            "availability": "UNAVAILABLE_PENDING_SETTLEMENT_INTEGRATION",
        },
        "disclaimer": "DEMO fills do not change paper balance and are not realized trades.",
    }
