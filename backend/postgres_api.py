"""Isolated Supabase PostgreSQL API for owner authentication and read-only status.

Run separately from legacy main.py until all trading routes are migrated.
No broker integration, no live-money operations, no MongoDB dependency.
"""
from contextlib import asynccontextmanager
from hmac import compare_digest
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import psycopg

import postgres_identity
import postgres_ledger
import postgres_state
import postgres_cycle
import postgres_accounting
import postgres_demo_orders
from demo_execution import DemoOrderError

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


class Credentials(BaseModel):
    username: str
    password: str


def connect():
    dsn = os.getenv("DATABASE_URL", "")
    if not dsn.startswith(("postgresql://", "postgres://")):
        raise RuntimeError("DATABASE_URL must be a server-side PostgreSQL DSN")
    return psycopg.connect(dsn, connect_timeout=8)


@asynccontextmanager
async def lifespan(app: FastAPI):
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("select to_regclass('playgo_private.owners')")
            if cur.fetchone()[0] is None:
                raise RuntimeError("Supabase private schema has not been applied")
            cur.execute("select to_regclass('playgo_private.documents')")
            if cur.fetchone()[0] is None:
                raise RuntimeError("Supabase state schema has not been applied")
        postgres_accounting.initialize(conn)
        postgres_state.initialize(conn)
    yield


app = FastAPI(title="PlayGo Paper Trading PostgreSQL API", lifespan=lifespan)
origins = [x.strip() for x in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if x.strip()]
if "*" in origins:
    raise RuntimeError("Wildcard CORS_ORIGINS is forbidden")
app.add_middleware(CORSMiddleware, allow_origins=origins,
                   allow_methods=["GET", "POST"], allow_headers=["Authorization", "Content-Type", "X-PlayGo-Bootstrap-Secret"])


def owner(authorization: str) -> str:
    try:
        with connect() as conn:
            return postgres_identity.verify_session(conn, authorization)
    except postgres_identity.OwnerAuthError as exc:
        raise HTTPException(401, str(exc)) from exc


@app.get("/api/health")
def health():
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("select 1")
            cur.fetchone()
    return {"ok": True, "mode": "PAPER", "database": "POSTGRESQL"}


@app.post("/api/identity/bootstrap-owner")
def bootstrap_owner(payload: Credentials, request: Request,
                    x_playgo_bootstrap_secret: str = Header(default="")):
    # Bootstrap is intentionally unavailable from deployed public networks.
    if request.client is None or request.client.host not in ("127.0.0.1", "::1"):
        raise HTTPException(403, "Bootstrap requires local access")
    secret = os.getenv("PLAYGO_OWNER_BOOTSTRAP_SECRET", "")
    if len(secret) < 32 or not compare_digest(secret, x_playgo_bootstrap_secret):
        raise HTTPException(403, "Bootstrap disabled or unauthorized")
    try:
        with connect() as conn:
            return postgres_identity.bootstrap_owner(conn, **payload.model_dump())
    except postgres_identity.OwnerAuthError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.post("/api/identity/register")
def register_disabled():
    raise HTTPException(403, "Public registration disabled")


@app.post("/api/identity/login")
def login(payload: Credentials):
    try:
        with connect() as conn:
            return postgres_identity.login(conn, **payload.model_dump())
    except postgres_identity.OwnerAuthError as exc:
        raise HTTPException(401, str(exc)) from exc


@app.post("/api/identity/logout")
def logout(authorization: str = Header(default="")):
    try:
        with connect() as conn:
            postgres_identity.revoke_session(conn, authorization)
    except postgres_identity.OwnerAuthError as exc:
        raise HTTPException(401, str(exc)) from exc
    return {"revoked": True}


@app.get("/api/identity/me/paper-account")
def paper_account(authorization: str = Header(default="")):
    owner_id = owner(authorization)
    return {"company_id": postgres_identity.COMPANY_ID, "user_id": owner_id,
            "role": "OWNER", "mode": "PAPER", "personal_account": False}


@app.get("/api/ledger/events")
def ledger_events(limit: int = 50, authorization: str = Header(default="")):
    owner(authorization)
    if not 1 <= limit <= 200:
        raise HTTPException(400, "Invalid limit")
    with connect() as conn:
        return {"mode": "PAPER", "events": postgres_ledger.recent_events(conn, limit)}


@app.get("/api/accounting/reconciliation")
def reconciliation(authorization: str = Header(default="")):
    owner(authorization)
    with connect() as conn:
        return postgres_accounting.reconcile(conn)


@app.get("/api/accounting/journals")
def journals(limit: int = 50, authorization: str = Header(default="")):
    owner(authorization)
    if not 1 <= limit <= 200:
        raise HTTPException(400, "Invalid limit")
    with connect() as conn:
        return {"mode": "PAPER", "currency": "USD",
                "journals": postgres_accounting.recent_journals(conn, limit)}


class DemoOrderRequest(BaseModel):
    client_order_id: str
    pair: str
    side: str
    units: int
    bid: str
    ask: str
    slippage_pips: str = "0.2"


@app.post("/api/demo/orders")
def submit_demo_order(payload: DemoOrderRequest, authorization: str = Header(default="")):
    owner(authorization)
    try:
        with connect() as conn:
            return postgres_demo_orders.submit_demo_order(conn, **payload.model_dump())
    except (DemoOrderError, ValueError) as exc:
        status = 409 if isinstance(exc, postgres_demo_orders.OrderConflict) else 400
        raise HTTPException(status, str(exc)) from exc


@app.get("/api/demo/orders/pending")
def pending_demo_orders(limit: int = 50, authorization: str = Header(default="")):
    owner(authorization)
    if not 1 <= limit <= 200:
        raise HTTPException(400, "Invalid limit")
    with connect() as conn:
        return {"mode": "DEMO", "orders": postgres_demo_orders.pending_orders(conn, limit)}


@app.post("/api/demo/orders/recover")
def recover_demo_orders(limit: int = 50, authorization: str = Header(default="")):
    owner(authorization)
    if not 1 <= limit <= 200:
        raise HTTPException(400, "Invalid limit")
    with connect() as conn:
        return postgres_demo_orders.recover_pending(conn, limit)


@app.get("/api/state")
def paper_state(authorization: str = Header(default="")):
    """Return the authoritative persisted paper state; no public write route."""
    owner(authorization)
    with connect() as conn:
        return {"mode": "PAPER", "state": postgres_state.load(conn)}


class PaperControlRequest(BaseModel):
    expected_revision: int
    paused: bool


@app.post("/api/state/control")
def paper_control(payload: PaperControlRequest,
                  authorization: str = Header(default="")):
    owner(authorization)
    try:
        with connect() as conn:
            state = postgres_state.set_paused(conn, **payload.model_dump())
        return {"mode": "PAPER", "state": state}
    except postgres_ledger.StaleStateError as exc:
        raise HTTPException(409, "State revision changed; reload and retry") from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


class PaperCycleRequest(BaseModel):
    expected_revision: int


@app.post("/api/auto-cycle")
def synthetic_cycle(payload: PaperCycleRequest,
                    authorization: str = Header(default="")):
    """One synthetic observation cycle; does not place or close orders."""
    owner(authorization)
    try:
        with connect() as conn:
            state = postgres_cycle.run_cycle(
                conn, expected_revision=payload.expected_revision)
        return {"mode": "PAPER", "execution": "OBSERVATION_ONLY", "state": state}
    except postgres_ledger.StaleStateError as exc:
        raise HTTPException(409, "State revision changed; reload and retry") from exc
    except postgres_cycle.CycleCooldown as exc:
        raise HTTPException(429, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
