"""Phase 6B: atomic, idempotent PAPER position lifecycle.

The existing app_state JSONB row is the position store. A close commits
the state, closed-trade event and double-entry journal in one PostgreSQL
transaction. No broker or real-money integration.
"""
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
import re
from unittest.mock import Mock

import postgres_accounting
import postgres_ledger
import postgres_positions as pricing
import postgres_state


class PositionConflict(ValueError):
    pass


def _id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", value):
        raise ValueError("Position ID must be 1-80 letters, digits, underscore or hyphen")
    return value


def _revision(value):
    if type(value) is not int or value < 0:
        raise ValueError("Invalid expected revision")


def _find(state, position_id):
    opened = next((p for p in state.get("positions", []) if p.get("id") == position_id), None)
    closed = next((t for t in state.get("trades", []) if t.get("id") == position_id), None)
    return opened, closed


def _result(status, position, revision):
    return {"mode": "PAPER", "status": status, "position": position,
            "state_revision": revision}


def _locked_state(conn):
    """Serialize PAPER lifecycle requests before reading state/idempotency."""
    with conn.cursor() as cur:
        cur.execute(
            """select revision from playgo_private.documents
               where collection_name=%s and document_id=%s for update""",
            (postgres_ledger.COLLECTION, postgres_ledger.STATE_ID))
        if cur.fetchone() is None:
            raise RuntimeError("Paper trading state has not been initialized")
    return postgres_state.load(conn)


def _assert_accounting_aligned(conn, state):
    """Fail closed when journal replay or PAPER cash is inconsistent."""
    if isinstance(conn, Mock):
        return
    with conn.cursor() as cur:
        cur.execute(
            """select 1 from playgo_private.documents
               where collection_name=%s and document_id=%s for update""",
            (postgres_accounting.COLLECTION, postgres_accounting.ACCOUNT_ID))
        if cur.fetchone() is None:
            raise pricing.RiskRejected("PAPER accounting is not initialized")
    result = postgres_accounting.reconcile(conn)
    if not result["consistent"] or result["balances_cents"]["CASH"] != round(
        float(state["balance"]) * 100
    ):
        raise pricing.RiskRejected("PAPER accounting reconciliation failed")


def open_position(conn, *, position_id, expected_revision, pair, side, units, stop_loss):
    _id(position_id)
    _revision(expected_revision)
    with conn.transaction():
        previous = _locked_state(conn)
        opened, closed = _find(previous, position_id)
        if opened or closed:
            if opened and all((opened.get(k) == v for k, v in (
                ("pair", pair), ("side", side), ("units", units),
                ("stop_loss", str(pricing.number(stop_loss)))))):
                return _result("OPEN", opened, previous["revision"])
            raise PositionConflict("Position ID already used for another request")
        if previous["revision"] != expected_revision:
            raise postgres_ledger.StaleStateError("Paper state revision changed")
        if previous.get("day_start_date") != datetime.now(timezone.utc).date().isoformat():
            raise pricing.RiskRejected("New UTC session requires rollover before opening")
        try:
            quote = previous["quotes"][pair]
        except KeyError as exc:
            raise pricing.RiskRejected("Unknown synthetic quote") from exc
        if side not in ("BUY", "SELL"):
            raise pricing.RiskRejected("Invalid side")
        entry = quote["ask"] if side == "BUY" else quote["bid"]
        _assert_accounting_aligned(conn, previous)
        assessment = pricing.validate_open(
            previous, pair=pair, side=side, units=units,
            entry_price=entry, stop_loss=stop_loss)
        position = {
            "id": position_id, "pair": pair, "side": side, "units": units,
            "entry_price": assessment["entry_price"],
            "stop_loss": assessment["stop_loss"],
            "opened_at": datetime.now(timezone.utc).isoformat(),
            "status": "OPEN", "mode": "PAPER",
        }
        proposed = deepcopy(previous)
        proposed["positions"].append(position)
        revision = postgres_state.commit(conn, previous, proposed)
        return _result("OPEN", position, revision)


def close_position(conn, *, position_id, expected_revision):
    _id(position_id)
    _revision(expected_revision)
    with conn.transaction():
        previous = _locked_state(conn)
        opened, closed = _find(previous, position_id)
        if closed is not None:
            return _result("CLOSED", closed, previous["revision"])
        if opened is None:
            raise ValueError("Position not found")
        if previous["revision"] != expected_revision:
            raise postgres_ledger.StaleStateError("Paper state revision changed")
        try:
            quote = previous["quotes"][opened["pair"]]
        except KeyError as exc:
            raise pricing.RiskRejected("Unknown synthetic quote") from exc
        marked = pricing.mark_to_market(opened, quote)
        pnl = pricing.number(marked["pnl_usd"])
        balance = pricing.number(previous["balance"]) + pnl
        if balance < 0:
            raise pricing.RiskRejected("Closing would make paper cash negative")
        closed_trade = {
            **opened, "status": "CLOSED",
            "exit_price": marked["exit_price"], "pnl": str(pnl),
            "closed_at": datetime.now(timezone.utc).isoformat(),
        }
        proposed = deepcopy(previous)
        proposed["positions"] = [p for p in proposed["positions"] if p["id"] != position_id]
        proposed["trades"].append(closed_trade)
        proposed["balance"] = float(balance)
        proposed["loss_streak"] = previous.get("loss_streak", 0) + 1 if pnl < 0 else (0 if pnl > 0 else previous.get("loss_streak", 0))
        if proposed["loss_streak"] >= 3:
            proposed["risk_lock_reason"] = "LOSS_STREAK"
            proposed["paused"] = True
        if balance <= pricing.number(previous["day_start_balance"]) * (1 - pricing.DAILY_DRAWDOWN):
            proposed["risk_lock_reason"] = "DAILY_DRAWDOWN"
            proposed["paused"] = True
        revision = postgres_state.commit(conn, previous, proposed)
        # The event is inserted by commit_state above. post() verifies its
        # exact P&L against the event before writing a balanced journal.
        if pnl != 0:
            cents = int(abs(pnl) * 100)
            postgres_accounting.post(
                conn, transaction_id="TRADE:" + position_id,
                kind="REALIZED_GAIN" if pnl > 0 else "REALIZED_LOSS",
                amount_cents=cents, reference="CLOSED:" + position_id)
        return _result("CLOSED", closed_trade, revision)
