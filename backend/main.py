"""PlayGo Forex paper-trading starter. Synthetic quotes only; never routes live orders."""

from contextlib import asynccontextmanager
from copy import deepcopy
import csv
from io import StringIO
from datetime import datetime, timezone
import os
from pathlib import Path
import random
from typing import Any, AsyncIterator
from uuid import uuid4
import agents
import feed
import broker
import periods
import reconciliation
import ledger
import demo_orders
import accounting
import settlement
import settlement_audit
import access_policy
import identity
import company
from demo_execution import DemoOrderError

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.errors import PyMongoError

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

PAIRS = {
    "EURUSD": (1.085, 0.0001, 0.00012),
    "GBPUSD": (1.265, 0.0001, 0.00018),
    "USDJPY": (151.0, 0.01, 0.018),
}
STATE_ID = "paper-trading-state"


def new_state() -> dict[str, Any]:
    quotes = {}
    for pair, (mid, pip, spread) in PAIRS.items():
        precision = 5 if pip < 0.01 else 3
        quotes[pair] = {
            "bid": round(mid - spread / 2, precision),
            "ask": round(mid + spread / 2, precision),
            "pip": pip,
            "spread": spread,
        }
    return {
        "balance": 10000.0,
        "starting_balance": 10000.0,
        "day_start_balance": 10000.0,
        "day_start_date": datetime.now(timezone.utc).date().isoformat(),
        "positions": [],
        "history": {},
        "signals": [],
        "trades": [],
        "logs": [],
        "paused": True,
        "quotes": quotes,
        "feed_type": "SYNTHETIC",
        "ticks": 0,
        "last_cycle_at": None,
        "loss_streak": 0,
        "risk_lock_reason": None,
        "equity_history": [],
        "revision": 0,
    }


state = new_state()
state_collection: Collection | None = None
ledger_collection: Collection | None = None
demo_order_collection: Collection | None = None
accounting_collection: Collection | None = None
accounting_journals: Collection | None = None
identity_users: Collection | None = None
identity_sessions: Collection | None = None
user_paper_accounts: Collection | None = None
mongo_client: MongoClient | None = None
random.seed(12)


def restore_state(previous_state: dict[str, Any]) -> None:
    state.clear()
    state.update(previous_state)


def persist_state(previous_state: dict[str, Any]) -> None:
    """Atomic compare-and-swap plus closed-trade event insertion.

    Fail closed when MongoDB transactions are unavailable.
    """
    if state_collection is None or ledger_collection is None:
        restore_state(previous_state)
        raise HTTPException(503, "MongoDB transaction collections unavailable")
    try:
        revision = ledger.commit_state(
            state_collection, ledger_collection, previous_state, state,
        )
        state["revision"] = revision
    except ledger.StaleStateError as exc:
        restore_state(previous_state)
        raise HTTPException(409, "Stale account state; reload before retrying") from exc
    except PyMongoError as exc:
        restore_state(previous_state)
        raise HTTPException(503, "Atomic MongoDB transaction failed; no changes committed") from exc



@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    global mongo_client, state_collection, ledger_collection, demo_order_collection, accounting_collection, accounting_journals, identity_users, identity_sessions, user_paper_accounts

    uri = os.getenv("MONGODB_URI")
    if not uri:
        raise RuntimeError(
            "MONGODB_URI is required. Add your MongoDB Atlas connection string "
            "to the project .env file."
        )

    client = MongoClient(uri, serverSelectionTimeoutMS=5000, appname="PlayGo AI Trading")
    database_name = os.getenv("MONGODB_DATABASE", "playgo_trading")
    collection = client[database_name]["app_state"]
    audit_collection = client[database_name]["paper_trade_ledger"]
    demo_collection = client[database_name]["demo_order_intents"]
    books_collection = client[database_name]["paper_accounting_accounts"]
    journal_collection = client[database_name]["paper_accounting_journals"]
    users_collection = client[database_name]["dev_identity_users"]
    sessions_collection = client[database_name]["dev_identity_sessions"]
    user_accounts_collection = client[database_name]["user_paper_accounts"]
    try:
        client.admin.command("ping")
        users_collection.create_index("username", unique=True)
        users_collection.create_index(
            "company_id", unique=True,
            partialFilterExpression={"company_id": company.COMPANY_ID},
            name="single_playgo_owner",
        )
        sessions_collection.create_index("expires_at", expireAfterSeconds=0)
        user_accounts_collection.create_index("user_id", unique=True)
        books_collection.update_one({"_id": accounting.ACCOUNT_ID}, {"$setOnInsert": accounting.opening_account()}, upsert=True)
        document = collection.find_one({"_id": STATE_ID})
        if document is None:
            collection.insert_one({"_id": STATE_ID, **state})
        else:
            if "revision" not in document:
                # Migration of existing paper-only document; concurrent startup is guarded.
                collection.update_one({"_id": STATE_ID, "revision": {"$exists": False}}, {"$set": {"revision": 0}})
                document = collection.find_one({"_id": STATE_ID})
            document.pop("_id", None)
            missing = set(state) - set(document)
            for key in missing:
                document[key] = deepcopy(state[key])
            state.clear()
            state.update(document)
    except PyMongoError as exc:
        client.close()
        raise RuntimeError(
            "Could not connect to MongoDB Atlas or load application state. "
            "Check the connection string, database user permissions, and Atlas network access."
        ) from exc
    except RuntimeError:
        client.close()
        raise

    mongo_client = client
    state_collection = collection
    ledger_collection = audit_collection
    demo_order_collection = demo_collection
    accounting_collection = books_collection
    accounting_journals = journal_collection
    identity_users = users_collection
    identity_sessions = sessions_collection
    user_paper_accounts = user_accounts_collection
    try:
        yield
    finally:
        state_collection = None
        ledger_collection = None
        demo_order_collection = None
        accounting_collection = None
        accounting_journals = None
        identity_users = None
        identity_sessions = None
        user_paper_accounts = None
        mongo_client = None
        client.close()


app = FastAPI(title="PlayGo AI Trading", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    ).split(","),
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.middleware("http")
async def protect_api_endpoints(request: Request, call_next):
    """Protect all private API reads and writes; never trust CORS as auth."""
    allowed, status, detail = access_policy.authorize(
        path=request.url.path,
        method=request.method,
        headers=request.headers,
        peer=request.client.host if request.client else "",
    )
    if not allowed:
        return JSONResponse(status_code=status, content={"detail": detail},
                            headers={"Cache-Control": "no-store"})
    return await call_next(request)


def log(agent: str, message: str) -> None:
    state["logs"].insert(
        0,
        {
            "id": str(uuid4()),
            "time": datetime.now(timezone.utc).isoformat(),
            "agent": agent,
            "message": message,
        },
    )
    state["logs"] = state["logs"][:100]


def equity() -> float:
    pnl = sum(
        (
            state["quotes"][position["pair"]]["bid"] - position["entry"]
            if position["side"] == "BUY"
            else position["entry"] - state["quotes"][position["pair"]]["ask"]
        )
        * position["units"]
        for position in state["positions"]
    )
    return round(state["balance"] + pnl, 2)


def risk_status() -> dict[str, Any]:
    today = datetime.now(timezone.utc).date().isoformat()
    current_equity = equity()
    daily_limit = current_equity <= state["day_start_balance"] * 0.98
    streak_limit = state.get("loss_streak", 0) >= 3
    reason = state.get("risk_lock_reason")
    if daily_limit:
        reason = "DAILY_DRAWDOWN"
    elif streak_limit:
        reason = "CONSECUTIVE_LOSSES"
    return {
        "session_date_utc": state["day_start_date"],
        "current_date_utc": today,
        "day_start_equity": state["day_start_balance"],
        "loss_streak": state.get("loss_streak", 0),
        "max_loss_streak": 3,
        "drawdown_limit_pct": 2.0,
        "locked": bool(reason),
        "reason": reason,
    }


def refresh_risk_session() -> None:
    """Reset daily baseline on UTC rollover, preserving manual pause and positions."""
    today = datetime.now(timezone.utc).date().isoformat()
    if state["day_start_date"] != today:
        state["day_start_date"] = today
        state["day_start_balance"] = equity()
        state["loss_streak"] = 0
        state["risk_lock_reason"] = None
        state["paused"] = True
        log("Supervisor", "New UTC session: risk counters reset; manual restart required")


def enforce_risk_limits() -> None:
    status = risk_status()
    if status["locked"]:
        state["risk_lock_reason"] = status["reason"]
        if not state["paused"]:
            state["paused"] = True
            log("Supervisor", f'New entries suspended: {status["reason"]}')


def performance() -> dict[str, Any]:
    """Realized paper P&L only; open-position P&L is excluded from win rate."""
    trades = state["trades"]
    wins = sum(1 for trade in trades if trade["pnl"] > 0)
    losses = sum(1 for trade in trades if trade["pnl"] < 0)
    realized = round(sum(trade["pnl"] for trade in trades), 2)
    return {
        "closed_trades": len(trades),
        "wins": wins,
        "losses": losses,
        "win_rate_pct": round(100 * wins / len(trades), 2) if trades else 0.0,
        "realized_pnl": realized,
        "unrealized_pnl": round(equity() - state["balance"], 2),
        "net_pnl": round(equity() - state["starting_balance"], 2),
    }


def record_equity_sample() -> None:
    """Store bounded, timestamped equity observations after market updates."""
    state.setdefault("equity_history", []).append({
        "time": datetime.now(timezone.utc).isoformat(),
        "equity": equity(),
    })
    state["equity_history"] = state["equity_history"][-500:]


def trading_analytics() -> dict[str, Any]:
    """Descriptive paper-only metrics; no performance forecasting."""
    samples = state.get("equity_history", [])
    peak = float(state["starting_balance"])
    max_drawdown = 0.0
    for sample in samples:
        value = float(sample["equity"])
        peak = max(peak, value)
        if peak > 0:
            max_drawdown = max(max_drawdown, (peak - value) / peak * 100)
    pairs = []
    for pair in ("EURUSD", "GBPUSD"):
        trades = [t for t in state["trades"] if t.get("pair") == pair]
        wins = sum(t["pnl"] > 0 for t in trades)
        pairs.append({
            "pair": pair, "closed_trades": len(trades),
            "wins": wins, "losses": sum(t["pnl"] < 0 for t in trades),
            "win_rate_pct": round(wins / len(trades) * 100, 2) if trades else 0.0,
            "realized_pnl": round(sum(t["pnl"] for t in trades), 2),
        })
    return {
        "equity_history": samples[-120:],
        "max_observed_drawdown_pct": round(max_drawdown, 2),
        "drawdown_sample_count": len(samples),
        "pair_performance": pairs,
    }


def decision_timeline() -> list[dict[str, Any]]:
    """Read-only unified view of persisted agent events; newest first."""
    categories = {
        "Scanner": "MARKET",
        "Strategy": "SIGNAL",
        "Risk Checker": "RISK",
        "Executor": "EXECUTION",
        "Logger": "CLOSE",
        "Supervisor": "CONTROL",
    }
    return [
        {
            "id": item["id"],
            "time": item["time"],
            "agent": item["agent"],
            "category": categories.get(item["agent"], "SYSTEM"),
            "message": item["message"],
        }
        for item in state.get("logs", [])[:100]
    ]


def snapshot() -> dict[str, Any]:
    return {
        "automation": agents.options(),
        "last_cycle_at": state.get("last_cycle_at"),
        "performance": performance(),
        "analytics": trading_analytics(),
        "risk": risk_status(),
        "decision_timeline": decision_timeline(),
        "price_history": {pair: values[-120:] for pair, values in state.get("history", {}).items() if pair in ("EURUSD", "GBPUSD")},
        "strategy_diagnostics": agents.diagnostics(state),
        "signals": state.get("signals", [])[-20:][::-1],
        "mode": "PAPER",
        "feed": state.get("feed_type", "SYNTHETIC"),
        "balance": round(state["balance"], 2),
        "equity": equity(),
        "paused": state["paused"],
        "positions": state["positions"],
        "trades": state["trades"][-30:][::-1],
        "logs": state["logs"][:30],
        "quotes": {k: v for k, v in state["quotes"].items() if k != "USDJPY" or state.get("feed_type") == "SYNTHETIC"},
        "agents": [
            "Scanner",
            "Strategy",
            "Risk Checker",
            "Executor",
            "Logger",
            "Supervisor",
        ],
    }


class Order(BaseModel):
    pair: str
    side: str
    stop_pips: float = 20
    take_profit_pips: float = 40


@app.get("/api/status")
def status() -> dict[str, Any]:
    return snapshot()


@app.post("/api/start")
def start() -> dict[str, Any]:
    previous_state = deepcopy(state)
    refresh_risk_session()
    enforce_risk_limits()
    if risk_status()["locked"]:
        persist_state(previous_state)
        raise HTTPException(403, "Risk supervisor lock is active; cannot restart entries")
    state["paused"] = False
    log("Supervisor", f"Paper engine enabled; configured feed: {os.getenv('FOREX_FEED', 'synthetic')}")
    persist_state(previous_state)
    return snapshot()


@app.post("/api/stop")
def stop() -> dict[str, Any]:
    previous_state = deepcopy(state)
    state["paused"] = True
    log("Supervisor", "New entries disabled; existing positions remain monitored")
    persist_state(previous_state)
    return snapshot()


@app.post("/api/tick")
def tick() -> dict[str, Any]:
    previous_state = deepcopy(state)
    refresh_risk_session()
    source = os.getenv("FOREX_FEED", "synthetic").lower()
    if source == "oanda_practice":
        try:
            fresh = feed.practice_quotes(("EURUSD", "GBPUSD"))
        except feed.FeedUnavailable as exc:
            state["paused"] = True
            log("Supervisor", "Practice feed failed; entries paused")
            persist_state(previous_state)
            raise HTTPException(503, str(exc)) from exc
        for pair, quote in fresh.items():
            state["quotes"][pair].update(quote)
        state["feed_type"] = "OANDA_PRACTICE"
    elif source == "synthetic":
        state["feed_type"] = "SYNTHETIC"
        for pair, (_, pip, spread) in PAIRS.items():
            quote = state["quotes"][pair]
            center = (quote["bid"] + quote["ask"]) / 2 + random.gauss(0, pip * 2)
            precision = 5 if pip < 0.01 else 3
            quote["bid"] = round(center - spread / 2, precision)
            quote["ask"] = round(center + spread / 2, precision)
    else:
        raise HTTPException(503, "Unsupported FOREX_FEED; quotes not updated")
    state["ticks"] += 1
    log("Scanner", f'Scanned {len(PAIRS)} pairs via {state["feed_type"]} (tick {state["ticks"]})')
    for position in list(state["positions"]):
        price = state["quotes"][position["pair"]][
            "bid" if position["side"] == "BUY" else "ask"
        ]
        hit = (
            price <= position["stop"] or price >= position["target"]
            if position["side"] == "BUY"
            else price >= position["stop"] or price <= position["target"]
        )
        if hit:
            close_position(position["id"], "SL/TP")
    enforce_risk_limits()
    record_equity_sample()
    persist_state(previous_state)
    return snapshot()


def close_position(position_id: str, reason: str) -> None:
    position = next(
        (item for item in state["positions"] if item["id"] == position_id),
        None,
    )
    if not position:
        raise HTTPException(404, "Position not found")
    quote = state["quotes"][position["pair"]]
    exit_price = quote["bid" if position["side"] == "BUY" else "ask"]
    pnl = round(
        (
            exit_price - position["entry"]
            if position["side"] == "BUY"
            else position["entry"] - exit_price
        )
        * position["units"],
        2,
    )
    state["balance"] = round(state["balance"] + pnl, 2)
    state["positions"].remove(position)
    state["trades"].append(
        {**position, "exit": exit_price, "pnl": pnl, "reason": reason,
         "closed_at": datetime.now(timezone.utc).isoformat()}
    )
    state["loss_streak"] = state.get("loss_streak", 0) + 1 if pnl < 0 else 0
    enforce_risk_limits()
    record_equity_sample()
    log(
        "Logger",
        f'Closed {position["pair"]} {position["side"]}: P&L ${pnl:.2f} ({reason})',
    )


@app.post("/api/orders")
def order(request: Order) -> dict[str, Any]:
    pair = request.pair.upper()
    side = request.side.upper()
    if state["paused"]:
        raise HTTPException(403, "Trading paused")
    if state["day_start_date"] != datetime.now(timezone.utc).date().isoformat():
        raise HTTPException(403, "New UTC session requires supervisor reset and manual restart")
    if risk_status()["locked"]:
        raise HTTPException(403, "Risk supervisor lock is active")
    if pair not in PAIRS or side not in ("BUY", "SELL"):
        raise HTTPException(400, "Unsupported pair or side")
    if not 5 <= request.stop_pips <= 100 or not 5 <= request.take_profit_pips <= 300:
        raise HTTPException(400, "Invalid stop or target distance")
    if len(state["positions"]) >= 3:
        raise HTTPException(400, "Maximum open positions reached")
    if any(position["pair"] == pair for position in state["positions"]):
        raise HTTPException(400, "Only one position per pair")
    if equity() <= state["day_start_balance"] * 0.98:
        raise HTTPException(400, "Daily equity drawdown limit")

    quote = state["quotes"][pair]
    if os.getenv("FOREX_FEED", "synthetic").lower() == "oanda_practice":
        timestamp = quote.get("timestamp")
        if not timestamp or quote.get("source") != "OANDA_PRACTICE" or (datetime.now(timezone.utc) - datetime.fromisoformat(timestamp)).total_seconds() > 120:
            raise HTTPException(400, "A fresh OANDA practice quote is required")
    pip = quote["pip"]
    entry = quote["ask" if side == "BUY" else "bid"]
    available_notional = max(0.0, equity() - sum(p["units"] * p["entry"] for p in state["positions"]))
    risk_budget = min(
        equity() * 0.005,
        max(
            0,
            equity() * 0.015
            - sum(position["risk_usd"] for position in state["positions"]),
        ),
    )
    effective_stop = request.stop_pips * pip + quote["spread"]
    units = min(int(risk_budget / effective_stop), int(available_notional / entry))
    if units < 1:
        raise HTTPException(400, "Insufficient risk budget")
    stop_price = entry + (-1 if side == "BUY" else 1) * request.stop_pips * pip
    target_price = entry + (1 if side == "BUY" else -1) * request.take_profit_pips * pip
    # USDJPY P&L is denominated in JPY; this starter uses USD quote pairs only for safe USD P&L.
    if pair == "USDJPY":
        raise HTTPException(
            400,
            "USDJPY disabled until quote-currency conversion is implemented",
        )
    if units * entry > available_notional:
        raise HTTPException(400, "Aggregate unleveraged notional exceeds equity")

    previous_state = deepcopy(state)
    position = {
        "id": str(uuid4()),
        "pair": pair,
        "side": side,
        "entry": entry,
        "stop": round(stop_price, 5),
        "target": round(target_price, 5),
        "units": units,
        "risk_usd": round(units * effective_stop, 2),
        "opened_at": datetime.now(timezone.utc).isoformat(),
    }
    state["positions"].append(position)
    log("Risk Checker", f'Approved {pair}: max risk ${position["risk_usd"]}')
    log("Executor", f'PAPER {side} {units} {pair} @ {entry}')
    persist_state(previous_state)
    return snapshot()


@app.post("/api/positions/{position_id}/close")
def close(position_id: str) -> dict[str, Any]:
    previous_state = deepcopy(state)
    close_position(position_id, "MANUAL")
    persist_state(previous_state)
    return snapshot()



REPORT_FIELDS = ("id", "pair", "side", "opened_at", "closed_at", "entry",
                 "exit", "stop", "target", "units", "risk_usd", "pnl", "reason")


def filtered_trades(pair: str = "ALL", side: str = "ALL",
                    outcome: str = "ALL") -> list[dict[str, Any]]:
    """Read-only closed paper trades, newest first."""
    if pair not in ("ALL", "EURUSD", "GBPUSD") or side not in ("ALL", "BUY", "SELL"):
        raise HTTPException(400, "Invalid trade filter")
    if outcome not in ("ALL", "WIN", "LOSS", "BREAKEVEN"):
        raise HTTPException(400, "Invalid outcome filter")
    rows = []
    for trade in reversed(state["trades"]):
        pnl = trade.get("pnl", 0)
        if pair != "ALL" and trade.get("pair") != pair:
            continue
        if side != "ALL" and trade.get("side") != side:
            continue
        if outcome == "WIN" and pnl <= 0:
            continue
        if outcome == "LOSS" and pnl >= 0:
            continue
        if outcome == "BREAKEVEN" and pnl != 0:
            continue
        rows.append({key: trade.get(key) for key in REPORT_FIELDS})
    return rows


@app.get("/api/reports/trades")
def trade_report(pair: str = "ALL", side: str = "ALL",
                 outcome: str = "ALL", limit: int = 50,
                 offset: int = 0) -> dict[str, Any]:
    if not 1 <= limit <= 200 or offset < 0:
        raise HTTPException(400, "Invalid pagination")
    rows = filtered_trades(pair, side, outcome)
    return {"total": len(rows), "limit": limit, "offset": offset,
            "trades": rows[offset:offset + limit]}


@app.get("/api/reports/trades.csv")
def trade_report_csv(pair: str = "ALL", side: str = "ALL",
                     outcome: str = "ALL") -> Response:
    rows = filtered_trades(pair, side, outcome)
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=REPORT_FIELDS)
    writer.writeheader()
    for row in rows:
        # Prevent spreadsheet formula injection from untrusted string fields.
        safe = {key: ("'" + value if isinstance(value, str) and
                     value.startswith(("=", "+", "-", "@", "\t", "\r"))
                     else value) for key, value in row.items()}
        writer.writerow(safe)
    return Response(output.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="playgo-paper-trades.csv"',
                             "Cache-Control": "no-store"})


@app.get("/api/broker/capabilities")
def broker_capabilities() -> dict[str, Any]:
    """Public capability declaration; live trading is always disabled."""
    return broker.execution_policy()


@app.get("/api/analytics/periods")
def period_analytics() -> dict[str, Any]:
    """Completed virtual trade P&L grouped by UTC calendar windows."""
    return periods.summarize(state["trades"])


@app.get("/api/diagnostics/reconciliation")
def reconciliation_status() -> dict[str, Any]:
    """Read-only integrity check of the current paper account."""
    return reconciliation.reconcile(
        state["positions"], state["trades"],
        state["balance"], state["starting_balance"],
    )


@app.get("/api/ledger/events")
def ledger_events(limit: int = 50) -> dict[str, Any]:
    """Read-only immutable closed-trade event records."""
    if not 1 <= limit <= 200:
        raise HTTPException(400, "Invalid event limit")
    if ledger_collection is None:
        raise HTTPException(503, "Ledger unavailable")
    try:
        return {"mode": "PAPER", "events": ledger.recent_events(ledger_collection, limit)}
    except PyMongoError as exc:
        raise HTTPException(503, "Unable to read trade ledger") from exc


class DemoOrderRequest(BaseModel):
    client_order_id: str
    pair: str
    side: str
    units: int
    bid: str
    ask: str
    slippage_pips: str = "0.2"


@app.post("/api/demo/orders")
def submit_demo_order(request: DemoOrderRequest) -> dict[str, Any]:
    """Localhost-only, independent simulated fills; does not touch paper balance."""
    if demo_order_collection is None:
        raise HTTPException(503, "Demo order store unavailable")
    try:
        return demo_orders.submit_demo_order(demo_order_collection, **request.model_dump())
    except (DemoOrderError, demo_orders.OrderConflict) as exc:
        raise HTTPException(409 if isinstance(exc, demo_orders.OrderConflict) else 400, str(exc)) from exc
    except PyMongoError as exc:
        raise HTTPException(503, "Demo order persistence unavailable") from exc


@app.get("/api/demo/orders/pending")
def pending_demo_orders(limit: int = 50) -> dict[str, Any]:
    if not 1 <= limit <= 200:
        raise HTTPException(400, "Invalid limit")
    if demo_order_collection is None:
        raise HTTPException(503, "Demo order store unavailable")
    try:
        return {"mode": "DEMO", "orders": demo_orders.pending_orders(demo_order_collection, limit)}
    except PyMongoError as exc:
        raise HTTPException(503, "Demo order store unavailable") from exc


@app.post("/api/demo/orders/recover")
def recover_demo_orders(limit: int = 50) -> dict[str, Any]:
    """Manual, localhost-only recovery; never invokes a broker."""
    if not 1 <= limit <= 200:
        raise HTTPException(400, "Invalid limit")
    if demo_order_collection is None:
        raise HTTPException(503, "Demo order store unavailable")
    try:
        return demo_orders.recover_pending(demo_order_collection, limit)
    except PyMongoError as exc:
        raise HTTPException(503, "Demo order recovery unavailable") from exc


class AccountingEntry(BaseModel):
    transaction_id: str
    kind: str
    amount_cents: int
    reference: str = ""


@app.post("/api/accounting/journals")
def accounting_post(entry: AccountingEntry) -> dict[str, Any]:
    """Localhost-only virtual accounting entry; no real money movement."""
    if accounting_collection is None or accounting_journals is None:
        raise HTTPException(503, "Accounting store unavailable")
    if entry.kind in ("REALIZED_GAIN", "REALIZED_LOSS"):
        raise HTTPException(403, "Realized P&L can only be posted through verified paper event settlement")
    try:
        return accounting.post(accounting_collection, accounting_journals, **entry.model_dump())
    except accounting.InsufficientFunds as exc:
        raise HTTPException(400, str(exc)) from exc
    except accounting.LedgerConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except PyMongoError as exc:
        raise HTTPException(503, "Atomic accounting write failed") from exc


@app.get("/api/accounting/reconciliation")
def accounting_reconciliation() -> dict[str, Any]:
    if accounting_collection is None or accounting_journals is None:
        raise HTTPException(503, "Accounting store unavailable")
    try:
        return accounting.reconcile(accounting_collection, accounting_journals)
    except PyMongoError as exc:
        raise HTTPException(503, "Accounting reconciliation unavailable") from exc


@app.get("/api/accounting/journals")
def accounting_recent_journals(limit: int = 50) -> dict[str, Any]:
    if not 1 <= limit <= 200:
        raise HTTPException(400, "Invalid journal limit")
    if accounting_journals is None:
        raise HTTPException(503, "Accounting store unavailable")
    try:
        rows = accounting_journals.find({"account_id": accounting.ACCOUNT_ID, "kind": {"$ne": "REVERSAL_CLAIM"}}).sort("created_at", -1).limit(limit)
        return {"mode": "PAPER", "currency": "USD", "journals": [accounting.public_journal(row) for row in rows]}
    except PyMongoError as exc:
        raise HTTPException(503, "Accounting journals unavailable") from exc


@app.post("/api/accounting/settle-paper-events")
def settle_paper_events(limit: int = 100) -> dict[str, Any]:
    """Localhost-only idempotent replay of persisted closed-paper-trade events."""
    if not 1 <= limit <= 200:
        raise HTTPException(400, "Invalid limit")
    if ledger_collection is None or accounting_collection is None or accounting_journals is None:
        raise HTTPException(503, "Paper ledger or accounting store unavailable")
    try:
        return settlement.settle_events(
            ledger_collection, accounting_collection, accounting_journals, limit
        )
    except PyMongoError as exc:
        raise HTTPException(503, "Paper settlement persistence unavailable") from exc


@app.get("/api/accounting/settlement-audit")
def paper_settlement_audit(limit: int = 200) -> dict[str, Any]:
    if not 1 <= limit <= 1000:
        raise HTTPException(400, "Invalid audit limit")
    if ledger_collection is None or accounting_journals is None:
        raise HTTPException(503, "Paper ledger or accounting store unavailable")
    try:
        return settlement_audit.audit(ledger_collection, accounting_journals, limit)
    except PyMongoError as exc:
        raise HTTPException(503, "Settlement audit unavailable") from exc


class RegisterIdentity(BaseModel):
    username: str
    password: str


@app.post("/api/identity/register")
def identity_register(payload: RegisterIdentity) -> dict[str, str]:
    raise HTTPException(403, "Public registration disabled; single PlayGo owner only")


@app.post("/api/identity/bootstrap-owner")
def bootstrap_company_owner(payload: RegisterIdentity, request: Request) -> dict[str, str]:
    """One-time local setup; requires out-of-band bootstrap secret."""
    if identity_users is None:
        raise HTTPException(503, "Identity store unavailable")
    from hmac import compare_digest
    secret = os.getenv("PLAYGO_OWNER_BOOTSTRAP_SECRET", "")
    supplied = request.headers.get("x-playgo-bootstrap-secret", "")
    if len(secret) < 32 or not compare_digest(secret, supplied):
        raise HTTPException(403, "Owner bootstrap disabled or unauthorized")
    try:
        return identity.register(identity_users, **payload.model_dump())
    except identity.IdentityError as exc:
        raise HTTPException(409, str(exc)) from exc
    except PyMongoError as exc:
        raise HTTPException(503, "Identity store unavailable") from exc


@app.post("/api/identity/login")
def identity_login(payload: RegisterIdentity) -> dict[str, Any]:
    if identity_users is None or identity_sessions is None:
        raise HTTPException(503, "Identity store unavailable")
    try:
        return identity.login(identity_users, identity_sessions, **payload.model_dump())
    except identity.IdentityError as exc:
        raise HTTPException(401, str(exc)) from exc
    except PyMongoError as exc:
        raise HTTPException(503, "Identity store unavailable") from exc


@app.get("/api/identity/me/paper-account")
def identity_my_paper_account(request: Request) -> dict[str, Any]:
    """Compatibility route: company ownership only; no personal balances."""
    if identity_sessions is None or identity_users is None:
        raise HTTPException(503, "Identity store unavailable")
    try:
        staff_id = identity.verify_session(identity_sessions, request.headers.get("authorization", ""))
        staff = identity_users.find_one({"_id": staff_id})
        if not staff:
            raise HTTPException(403, "Staff unavailable")
        context = company.require_permission(staff, "read")
        return {**context, "mode": "PAPER", "personal_account": False}
    except (identity.IdentityError, company.CompanyAccessError) as exc:
        raise HTTPException(403, str(exc)) from exc


@app.post("/api/identity/logout")
def identity_logout(request: Request) -> dict[str, bool]:
    if identity_sessions is None:
        raise HTTPException(503, "Session store unavailable")
    try:
        identity.revoke_session(identity_sessions, request.headers.get("authorization", ""))
        return {"revoked": True}
    except identity.IdentityError as exc:
        raise HTTPException(401, str(exc)) from exc
    except PyMongoError as exc:
        raise HTTPException(503, "Session store unavailable") from exc


@app.get("/api/company/migration-preview")
def company_migration_preview(request: Request) -> dict[str, Any]:
    if any(x is None for x in (identity_sessions, identity_users, state_collection, accounting_collection, accounting_journals)):
        raise HTTPException(503, "Company data unavailable")
    try:
        staff_id = identity.verify_session(identity_sessions, request.headers.get("authorization", ""))
        staff = identity_users.find_one({"_id": staff_id})
        if not staff:
            raise HTTPException(403, "Staff unavailable")
        company.require_permission(staff, "staff")
        legacy = state_collection.find_one({"_id": STATE_ID})
        book = accounting_collection.find_one({"_id": accounting.ACCOUNT_ID})
        count = accounting_journals.count_documents({"account_id": accounting.ACCOUNT_ID, "kind": {"$ne": "REVERSAL_CLAIM"}})
        return company.migration_preview(legacy or {}, book, count)
    except (identity.IdentityError, company.CompanyAccessError) as exc:
        raise HTTPException(403, str(exc)) from exc
    except PyMongoError as exc:
        raise HTTPException(503, "Migration preview unavailable") from exc


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"ok": True, "mode": "PAPER", "feed": state.get("feed_type", "SYNTHETIC")}


@app.post("/api/auto-cycle")
def auto_cycle() -> dict[str, Any]:
    """Explicit simulation step. Synthetic market data; never a broker order."""
    return agents.tick_cycle(__import__(__name__))


@app.get("/api/agents/config")
def agent_configuration() -> dict[str, Any]:
    return agents.options()
