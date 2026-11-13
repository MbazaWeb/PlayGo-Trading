"""PlayGo Forex paper-trading starter. Synthetic quotes only; never routes live orders."""

from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import datetime, timezone
import os
from pathlib import Path
import random
from typing import Any, AsyncIterator
from uuid import uuid4
import agents
import feed

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
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
    }


state = new_state()
state_collection: Collection | None = None
mongo_client: MongoClient | None = None
random.seed(12)


def restore_state(previous_state: dict[str, Any]) -> None:
    state.clear()
    state.update(previous_state)


def persist_state(previous_state: dict[str, Any]) -> None:
    if state_collection is None:
        restore_state(previous_state)
        raise HTTPException(
            status_code=503,
            detail="MongoDB is not connected; the request was not saved.",
        )
    try:
        state_collection.replace_one(
            {"_id": STATE_ID},
            {"_id": STATE_ID, **state},
            upsert=True,
        )
    except PyMongoError as exc:
        restore_state(previous_state)
        raise HTTPException(
            status_code=503,
            detail="MongoDB could not save the request; no changes were applied.",
        ) from exc


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    global mongo_client, state_collection

    uri = os.getenv("MONGODB_URI")
    if not uri:
        raise RuntimeError(
            "MONGODB_URI is required. Add your MongoDB Atlas connection string "
            "to the project .env file."
        )

    client = MongoClient(uri, serverSelectionTimeoutMS=5000, appname="PlayGo AI Trading")
    database_name = os.getenv("MONGODB_DATABASE", "playgo_trading")
    collection = client[database_name]["app_state"]
    try:
        client.admin.command("ping")
        document = collection.find_one({"_id": STATE_ID})
        if document is None:
            collection.insert_one({"_id": STATE_ID, **state})
        else:
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
    try:
        yield
    finally:
        state_collection = None
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
async def protect_write_endpoints(request: Request, call_next):
    """Until user authentication exists, reject writes outside local development."""
    if request.method == "POST" and request.url.path.startswith("/api/"):
        origin = request.headers.get("origin")
        allowed_origins = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
        if origin and origin not in allowed_origins:
            return JSONResponse(status_code=403, content={"detail": "Untrusted browser origin"})
        local_mode = os.getenv("PLAYGO_ENV", "local").lower() == "local"
        peer = request.client.host if request.client else ""
        if not local_mode or peer not in ("127.0.0.1", "::1", "testclient"):
            return JSONResponse(status_code=403, content={"detail": "Write endpoints are localhost-only in Phase 2."})
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
        "performance": performance(),
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
    if equity() <= state["day_start_balance"] * 0.98:
        raise HTTPException(403, "Daily drawdown limit is active; cannot restart entries")
    previous_state = deepcopy(state)
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
    if equity() <= state["day_start_balance"] * 0.98:
        state["paused"] = True
        log("Supervisor", "Daily equity drawdown limit triggered: entries disabled")
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
        {**position, "exit": exit_price, "pnl": pnl, "reason": reason}
    )
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
