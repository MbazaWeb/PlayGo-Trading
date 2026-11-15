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
from psycopg.conninfo import conninfo_to_dict

import postgres_identity
import postgres_ledger
import postgres_state
import postgres_cycle
import postgres_accounting
import postgres_demo_orders
import postgres_analytics
import postgres_positions
import postgres_position_lifecycle
import postgres_signal_store
import postgres_emergency_stop
import postgres_automated_risk
import postgres_risk_audit
from demo_execution import DemoOrderError

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


class Credentials(BaseModel):
    username: str
    password: str


def connect():
    dsn = os.getenv("DATABASE_URL", "")
    if not dsn:
        raise RuntimeError("DATABASE_URL must be configured server-side")
    try:
        params = conninfo_to_dict(dsn)
    except psycopg.ProgrammingError as exc:
        raise RuntimeError("DATABASE_URL must be a valid PostgreSQL connection string") from exc
    if not params.get("dbname") or not (params.get("host") or params.get("hostaddr")):
        raise RuntimeError("DATABASE_URL requires an explicit database and host")
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
        postgres_accounting.post(conn, transaction_id="OPENING:PAPER:USD:10000",
                                 kind="CAPITAL_IN", amount_cents=1_000_000,
                                 reference="SYNTHETIC_ACCOUNT_INITIALIZATION")
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
    # Proxies can make public requests appear to originate from loopback.
    # Require an explicit local deployment mode in addition to the secret.
    if os.getenv("PLAYGO_ENV", "").lower() != "local":
        raise HTTPException(403, "Owner bootstrap disabled outside local development")
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




@app.get("/api/demo/orders")
def demo_order_history(limit: int = 25, offset: int = 0, pair: str | None = None,
                       side: str | None = None, status: str | None = None,
                       date_from: str | None = None, date_to: str | None = None,
                       authorization: str = Header(default="")):
    owner(authorization)
    try:
        with connect() as conn:
            return postgres_demo_orders.list_orders(
                conn, limit=limit, offset=offset, pair=pair, side=side,
                status=status, date_from=date_from, date_to=date_to)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


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


@app.get("/api/demo/orders/{client_order_id}")
def demo_order_detail(client_order_id: str,
                      authorization: str = Header(default="")):
    owner(authorization)
    try:
        with connect() as conn:
            order = postgres_demo_orders.get_order(conn, client_order_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if order is None:
        raise HTTPException(404, "DEMO order not found")
    return order

class PaperPositionPreview(BaseModel):
    pair: str
    side: str
    units: int
    stop_loss: str


@app.post("/api/paper/positions/preview")
def preview_paper_position(payload: PaperPositionPreview,
                           authorization: str = Header(default="")):
    """Risk-check a hypothetical position; no position is opened."""
    owner(authorization)
    with connect() as conn:
        state = postgres_state.load(conn)
    try:
        quote = state["quotes"][payload.pair]
        entry = quote["ask"] if payload.side == "BUY" else quote["bid"]
        assessment = postgres_positions.validate_open(
            state, pair=payload.pair, side=payload.side, units=payload.units,
            entry_price=entry, stop_loss=payload.stop_loss)
    except KeyError as exc:
        raise HTTPException(400, "Unknown synthetic quote") from exc
    except postgres_positions.RiskRejected as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"mode": "PAPER", "execution": "PREVIEW_ONLY",
            "state_revision": state["revision"], "assessment": assessment}


class PaperPositionOpen(BaseModel):
    position_id: str
    expected_revision: int
    pair: str
    side: str
    units: int
    stop_loss: str


class PaperPositionClose(BaseModel):
    expected_revision: int


@app.post("/api/paper/positions")
def open_paper_position(payload: PaperPositionOpen,
                        authorization: str = Header(default="")):
    owner(authorization)
    try:
        with connect() as conn:
            return postgres_position_lifecycle.open_position(conn, **payload.model_dump())
    except postgres_ledger.StaleStateError as exc:
        raise HTTPException(409, "State revision changed; reload and retry") from exc
    except postgres_position_lifecycle.PositionConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except (postgres_positions.RiskRejected, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/paper/positions/{position_id}/close")
def close_paper_position(position_id: str, payload: PaperPositionClose,
                         authorization: str = Header(default="")):
    owner(authorization)
    try:
        with connect() as conn:
            return postgres_position_lifecycle.close_position(
                conn, position_id=position_id, expected_revision=payload.expected_revision)
    except postgres_ledger.StaleStateError as exc:
        raise HTTPException(409, "State revision changed; reload and retry") from exc
    except (postgres_positions.RiskRejected, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/analytics/overview")
def analytics_overview(authorization: str = Header(default="")):
    owner(authorization)
    with connect() as conn:
        return postgres_analytics.snapshot(conn)


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


class PaperSignalRequest(BaseModel):
    signal_id: str
    pair: str
    side: str
    confidence: str
    timestamp: str
    stop_loss: str


@app.post("/api/paper/signals")
def submit_paper_signal(payload: PaperSignalRequest,
                        authorization: str = Header(default="")):
    """Owner-authenticated signal audit; never submits a PAPER order."""
    owner(authorization)
    try:
        with connect() as conn:
            return postgres_signal_store.record_signal(
                conn, signal=payload.model_dump())
    except postgres_signal_store.SignalConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/paper/signals")
def paper_signal_history(limit: int = 25, offset: int = 0,
                         authorization: str = Header(default="")):
    owner(authorization)
    try:
        with connect() as conn:
            return postgres_signal_store.list_signals(
                conn, limit=limit, offset=offset)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/paper/signals/{signal_id}")
def paper_signal_detail(signal_id: str,
                        authorization: str = Header(default="")):
    owner(authorization)
    try:
        with connect() as conn:
            decision = postgres_signal_store.get_signal(conn, signal_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if decision is None:
        raise HTTPException(404, "PAPER signal not found")
    return decision


class PaperEmergencyStopRequest(BaseModel):
    expected_revision: int
    reason: str


@app.post("/api/paper/automation/emergency-stop")
def paper_automation_emergency_stop(payload: PaperEmergencyStopRequest,
                                    authorization: str = Header(default="")):
    """Owner-only, one-way emergency stop; no automated execution."""
    owner(authorization)
    try:
        with connect() as conn:
            state = postgres_emergency_stop.engage(conn, **payload.model_dump())
        return {"mode": "PAPER", "execution": "DISABLED",
                "emergency_stop": True, "state": state}
    except postgres_ledger.StaleStateError as exc:
        raise HTTPException(409, "State revision changed; reload and retry") from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


class PaperAutomatedRiskPreview(BaseModel):
    pair: str
    side: str
    units: int
    entry_price: str
    stop_loss: str


@app.post("/api/paper/automation/risk-preview")
def paper_automation_risk_preview(payload: PaperAutomatedRiskPreview,
                                  authorization: str = Header(default="")):
    """Owner-only observation; automation remains disabled regardless of eligibility.

    Reads the authoritative state and reconciled accounting in a single
    read-only repeatable-read transaction to avoid inconsistent snapshots.
    """
    owner(authorization)
    with connect() as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                cur.execute("set transaction isolation level repeatable read, read only")
            state = postgres_state.load(conn)
            accounting = postgres_accounting.reconcile(conn)
            decision = postgres_automated_risk.assess(
                state, accounting, proposal=payload.model_dump(),
                automation_enabled=False)
    return {"mode": "PAPER", "execution": "OBSERVATION_ONLY",
            "state_revision": state["revision"], "decision": decision}


class PaperRiskAuditRequest(BaseModel):
    assessment_id: str
    proposal: PaperAutomatedRiskPreview


@app.post("/api/paper/automation/risk-assessments")
def record_paper_risk_assessment(payload: PaperRiskAuditRequest,
                                 authorization: str = Header(default="")):
    """Explicitly persist a risk decision; no account state mutation."""
    owner(authorization)
    try:
        with connect() as conn:
            return postgres_risk_audit.record(
                conn, assessment_id=payload.assessment_id,
                proposal=payload.proposal.model_dump())
    except postgres_risk_audit.AuditConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/paper/automation/risk-assessments")
def paper_risk_assessment_history(limit: int = 25, offset: int = 0,
                                  authorization: str = Header(default="")):
    owner(authorization)
    try:
        with connect() as conn:
            return postgres_risk_audit.list_recent(
                conn, limit=limit, offset=offset)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/paper/automation/risk-assessments/{assessment_id}")
def paper_risk_assessment_detail(assessment_id: str,
                                 authorization: str = Header(default="")):
    owner(authorization)
    try:
        with connect() as conn:
            result = postgres_risk_audit.get(conn, assessment_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if result is None:
        raise HTTPException(404, "Risk assessment not found")
    return result
