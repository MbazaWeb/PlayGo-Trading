"""Page-driven, demo-only Deriv Options bot with a persisted stake budget."""
import asyncio
import hashlib
import json
import re
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from urllib.parse import parse_qs, quote, urlsplit

import httpx
import psycopg
import websockets
from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.agents import signal as ema_signal
from app.deriv_accounts import parse_accounts
from app.deriv_market_data import DerivMarketDataError, parse_candles
from app.postgres_api import connect

router = APIRouter()
COLLECTION = "deriv_demo_bots"
API_BASE = "https://api.derivws.com"
SYMBOL = "frxEURUSD"
GRANULARITY = 300
DURATION_MINUTES = 5
STAKE = Decimal("2")
DAILY_STAKE_LIMIT = Decimal("5")
MAX_CANDLE_AGE = 600


class DemoBotRequest(BaseModel):
    account_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")


class DemoBotResolveRequest(DemoBotRequest):
    confirmed_account_review: bool


class DemoBotProviderError(ValueError):
    pass


def _account_document_id(account_id):
    return hashlib.sha256(account_id.encode()).hexdigest()


def _utc_day():
    return datetime.now(timezone.utc).date().isoformat()


def _empty_state(account_id):
    return {
        "account_id": account_id,
        "running": False,
        "status": "stopped",
        "day": _utc_day(),
        "daily_stake": "0",
        "last_processed_epoch": 0,
        "active_contract_id": None,
        "active_until": 0,
        "pending_trade": None,
        "last_trade": None,
        "last_cycle_at": None,
        "last_error": None,
    }


def _decode_state(row, account_id):
    if row is None:
        return _empty_state(account_id)
    try:
        body = row[0] if isinstance(row[0], dict) else json.loads(row[0])
        state = body.get("bot") if isinstance(body, dict) else None
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(503, "Demo bot state is invalid. Contact support.") from None
    if not isinstance(state, dict) or state.get("account_id") != account_id:
        raise HTTPException(503, "Demo bot state is invalid. Contact support.")
    return state


def _save_state(cursor, account_id, state):
    cursor.execute(
        """insert into playgo_private.documents
            (collection_name,document_id,body,revision)
            values (%s,%s,%s::jsonb,0)
            on conflict (collection_name,document_id) do update
            set body=excluded.body,
                revision=playgo_private.documents.revision+1""",
        (COLLECTION, _account_document_id(account_id), json.dumps({"bot": state})),
    )


def _sync_run_record(cursor, account_id, state, *, session_id=None):
    if session_id is not None:
        if not isinstance(session_id, str) or not re.fullmatch(r"[0-9a-f]{64}", session_id):
            raise RuntimeError("Invalid Deriv session identifier")
        config = {
            "strategy": "EMA_9_21_CROSS",
            "execution": "DEMO_ONLY",
            "symbol": SYMBOL,
            "contract_type": "CALL_ON_UP_CROSS_PUT_ON_DOWN_CROSS",
            "duration_minutes": DURATION_MINUTES,
            "currency": state["currency"],
            "stake": str(STAKE),
            "daily_stake_limit": str(DAILY_STAKE_LIMIT),
        }
        cursor.execute(
            """insert into playgo_private.bot_runs
                (session_id, account_id, status, config)
                values (%s, %s, 'running', %s::jsonb)
                returning id""",
            (session_id, account_id, json.dumps(config)),
        )
        row = cursor.fetchone()
        if not row:
            raise RuntimeError("Demo bot run could not be recorded")
        state["run_id"] = str(row[0])
        return

    run_id = state.get("run_id")
    if not run_id:
        return
    status = (
        "running" if state["running"]
        else "error" if state["status"] in {"needs_review", "feed_error"}
        else "stopped"
    )
    cursor.execute(
        """update playgo_private.bot_runs
           set status = %s,
               updated_at = now(),
               stopped_at = case
                   when %s = 'running' then null
                   else coalesce(stopped_at, now())
               end
           where id = %s and account_id = %s
           returning id""",
        (status, status, run_id, account_id),
    )
    if not cursor.fetchone():
        raise RuntimeError("Demo bot run record could not be updated")


@contextmanager
def _locked_state(account_id, *, create=False, new_run_session_id=None):
    document_id = _account_document_id(account_id)
    with connect() as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                if create:
                    cur.execute(
                        """insert into playgo_private.documents
                            (collection_name,document_id,body,revision)
                            values (%s,%s,%s::jsonb,0)
                            on conflict (collection_name,document_id) do nothing""",
                        (COLLECTION, document_id, json.dumps({"bot": _empty_state(account_id)})),
                    )
                cur.execute(
                    """select body from playgo_private.documents
                       where collection_name=%s and document_id=%s for update""",
                    (COLLECTION, document_id),
                )
                state = _decode_state(cur.fetchone(), account_id)
                yield state
                _sync_run_record(
                    cur, account_id, state, session_id=new_run_session_id
                )
                _save_state(cur, account_id, state)


def _load_state(account_id):
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "select body from playgo_private.documents where collection_name=%s and document_id=%s",
                (COLLECTION, _account_document_id(account_id)),
            )
            return _decode_state(cur.fetchone(), account_id)


def _public_state(state):
    return {
        "execution": "DEMO_ONLY",
        "strategy": "EMA_9_21_CROSS",
        "symbol": SYMBOL,
        "contract_type": "CALL_ON_UP_CROSS_PUT_ON_DOWN_CROSS",
        "duration_minutes": DURATION_MINUTES,
        "stake": str(STAKE),
        "daily_stake_limit": str(DAILY_STAKE_LIMIT),
        **state,
    }


def _deriv_connection(authorization):
    if not authorization.startswith("Bearer deriv_"):
        raise HTTPException(401, "Sign in with Deriv to use the demo bot.")
    from app.deriv_signin import read_session
    try:
        return read_session(authorization)
    except HTTPException:
        raise
    except (psycopg.Error, OSError, RuntimeError):
        raise HTTPException(503, "Deriv sign-in is temporarily unavailable.") from None


async def _demo_account(access_token, account_id):
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                API_BASE + "/trading/v1/options/accounts",
                headers={"Authorization": "Bearer " + access_token},
            )
        if response.status_code in (401, 403):
            raise HTTPException(401, "Deriv authorization expired. Please sign in again.")
        response.raise_for_status()
        accounts = parse_accounts(response.json())
    except HTTPException:
        raise
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        raise HTTPException(502, "Unable to verify the Deriv demo account.") from None
    account = next((item for item in accounts if item["account_id"] == account_id), None)
    if account is None or account["account_type"] != "demo":
        raise HTTPException(403, "The bot can only use an authorized Deriv demo Options account.")
    if account["currency"] != "USD":
        raise HTTPException(400, "The demo bot is currently configured for USD accounts.")
    return account


async def _websocket_url(access_token, account_id):
    url = API_BASE + "/trading/v1/options/accounts/" + quote(account_id, safe="") + "/otp"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(url, headers={"Authorization": "Bearer " + access_token})
        response.raise_for_status()
        result = response.json()
    except (httpx.HTTPError, ValueError):
        raise DemoBotProviderError("Deriv could not open a demo trading connection.") from None
    ws_url = result.get("data", {}).get("url") if isinstance(result, dict) else None
    if not isinstance(ws_url, str):
        raise DemoBotProviderError("Deriv did not return a demo trading connection.")
    parsed = urlsplit(ws_url)
    otp = parse_qs(parsed.query).get("otp", [])
    if parsed.scheme != "wss" or parsed.hostname != "api.derivws.com" or parsed.path != "/trading/v1/options/ws/demo" or len(otp) != 1 or not otp[0]:
        raise DemoBotProviderError("Deriv returned an invalid demo trading connection.")
    return ws_url


async def _ws_request(socket, request, request_id):
    payload = {**request, "req_id": request_id}
    await socket.send(json.dumps(payload))
    for _ in range(32):
        try:
            message = json.loads(await asyncio.wait_for(socket.recv(), timeout=12))
        except (asyncio.TimeoutError, json.JSONDecodeError):
            raise DemoBotProviderError("Timed out waiting for Deriv demo trading data.") from None
        if not isinstance(message, dict):
            continue
        echoed = message.get("req_id")
        if echoed is None and isinstance(message.get("echo_req"), dict):
            echoed = message["echo_req"].get("req_id")
        if echoed != request_id:
            continue
        if message.get("error"):
            raise DemoBotProviderError("Deriv rejected a demo bot request.")
        return message
    raise DemoBotProviderError("Deriv did not return the expected demo bot response.")


def _reserve_signal(account_id, *, side, candle_epoch, now):
    with _locked_state(account_id) as state:
        if not state["running"]:
            return state, False
        day = datetime.fromtimestamp(now, timezone.utc).date().isoformat()
        if state["day"] != day:
            state["day"] = day
            state["daily_stake"] = "0"
        state["last_cycle_at"] = datetime.fromtimestamp(now, timezone.utc).isoformat()
        if state["pending_trade"]:
            pending_at = state["pending_trade"].get("created_at", 0)
            if now - pending_at > 120:
                state["running"] = False
                if state["pending_trade"].get("stage") == "proposal":
                    _release_proposal_stake(state)
                    state["status"] = "feed_error"
                    state["last_error"] = "The demo proposal did not complete. The bot was paused."
                else:
                    state["status"] = "needs_review"
                    state["last_error"] = "A trade result is uncertain. Check Deriv before restarting."
            return state, False
        if candle_epoch <= state["last_processed_epoch"]:
            return state, False
        state["last_processed_epoch"] = candle_epoch
        if state["active_until"] > now:
            state["status"] = "contract_open"
            return state, False
        if state["active_contract_id"] and state["last_trade"]:
            state["last_trade"]["status"] = "duration elapsed"
        state["active_contract_id"] = None
        state["active_until"] = 0
        if side is None:
            state["status"] = "running"
            return state, False
        daily_stake = Decimal(state["daily_stake"])
        if daily_stake + STAKE > DAILY_STAKE_LIMIT:
            state["running"] = False
            state["status"] = "daily_budget_reached"
            return state, False
        state["daily_stake"] = str(daily_stake + STAKE)
        state["status"] = "trade_pending"
        state["pending_trade"] = {
            "side": side,
            "candle_epoch": candle_epoch,
            "created_at": now,
            "stage": "proposal",
        }
        state["last_error"] = None
        return state, True


def _finish_trade(account_id, contract_id):
    with _locked_state(account_id) as state:
        pending = state["pending_trade"]
        if not pending:
            state["running"] = False
            state["status"] = "needs_review"
            state["last_error"] = "Trade state changed unexpectedly. Check Deriv before restarting."
            return state
        state["active_contract_id"] = str(contract_id)
        state["active_until"] = int(time.time()) + DURATION_MINUTES * 60 + 60
        state["last_trade"] = {
            "contract_id": str(contract_id),
            "side": pending["side"],
            "stake": str(STAKE),
            "created_at": datetime.fromtimestamp(pending["created_at"], timezone.utc).isoformat(),
            "status": "open",
        }
        state["pending_trade"] = None
        if state["running"]:
            state["status"] = "contract_open"
        else:
            state["status"] = "stopped"
            state["last_error"] = None
        return state


def _fail_trade(account_id, *, uncertain):
    with _locked_state(account_id) as state:
        state["running"] = False
        state["status"] = "needs_review" if uncertain else "feed_error"
        state["last_error"] = (
            "A trade result is uncertain. Check Deriv before restarting."
            if uncertain else "Deriv rejected the demo proposal. The bot was paused."
        )
        if not uncertain:
            _release_proposal_stake(state)
        return state


def _release_proposal_stake(state):
    pending = state.get("pending_trade")
    if pending and pending.get("stage") == "proposal":
        state["daily_stake"] = str(max(Decimal("0"), Decimal(state["daily_stake"]) - STAKE))
        state["pending_trade"] = None


def _mark_buy_started(account_id):
    with _locked_state(account_id) as state:
        if not state["pending_trade"] or state["pending_trade"].get("stage") != "proposal":
            raise DemoBotProviderError("The demo trade state changed unexpectedly.")
        state["pending_trade"]["stage"] = "buy"


async def _execute_trade(socket, state, side, account_id):
    contract_type = "CALL" if side == "BUY" else "PUT"
    proposal = await _ws_request(
        socket,
        {
            "proposal": 1,
            "amount": float(STAKE),
            "basis": "stake",
            "contract_type": contract_type,
            "currency": state["currency"],
            "duration": DURATION_MINUTES,
            "duration_unit": "m",
            "underlying_symbol": SYMBOL,
        },
        1,
    )
    details = proposal.get("proposal")
    if not isinstance(details, dict) or not isinstance(details.get("id"), str):
        raise DemoBotProviderError("Deriv returned an invalid demo price proposal.")
    try:
        ask_price = Decimal(str(details["ask_price"]))
    except (KeyError, InvalidOperation, TypeError, ValueError):
        raise DemoBotProviderError("Deriv returned an invalid demo price proposal.") from None
    if not ask_price.is_finite() or ask_price <= 0 or ask_price > STAKE:
        raise DemoBotProviderError("The demo contract price exceeded the configured stake.")
    _mark_buy_started(account_id)
    result = await _ws_request(socket, {"buy": details["id"], "price": float(ask_price)}, 2)
    bought = result.get("buy")
    if not isinstance(bought, dict):
        raise DemoBotProviderError("Deriv returned an invalid demo purchase response.")
    contract_id = bought.get("contract_id")
    if not isinstance(contract_id, (str, int)) or not str(contract_id).isdigit():
        raise DemoBotProviderError("Deriv returned an invalid demo contract ID.")
    return str(contract_id)


@router.get("/api/deriv/demo-bot")
async def get_demo_bot(account_id: str = Query(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$"),
                       authorization: str = Header(default="")):
    connection = _deriv_connection(authorization)
    await _demo_account(connection["access_token"], account_id)
    try:
        state = _load_state(account_id)
    except (psycopg.Error, OSError, RuntimeError, ValueError, TypeError, KeyError):
        raise HTTPException(503, "Demo bot status is temporarily unavailable.") from None
    return JSONResponse(_public_state(state), headers={"Cache-Control": "no-store"})


@router.post("/api/bot/start", include_in_schema=False)
@router.post("/api/deriv/demo-bot/start")
async def start_demo_bot(payload: DemoBotRequest, authorization: str = Header(default="")):
    connection = _deriv_connection(authorization)
    account = await _demo_account(connection["access_token"], payload.account_id)
    session_id = connection.get("session_digest")
    if not isinstance(session_id, str) or not re.fullmatch(r"[0-9a-f]{64}", session_id):
        raise HTTPException(401, "Invalid Deriv session. Please sign in again.")
    now = int(time.time())
    day = datetime.fromtimestamp(now, timezone.utc).date().isoformat()
    try:
        with _locked_state(
            payload.account_id, create=True, new_run_session_id=session_id
        ) as state:
            if state["pending_trade"]:
                if state["pending_trade"].get("stage") == "proposal":
                    _release_proposal_stake(state)
                else:
                    raise HTTPException(409, "A prior trade needs review before the bot can restart.")
            if state["running"]:
                raise HTTPException(409, "The demo bot is already running.")
            if state["day"] != day:
                state["day"] = day
                state["daily_stake"] = "0"
            if Decimal(state["daily_stake"]) + STAKE > DAILY_STAKE_LIMIT:
                raise HTTPException(409, "The daily demo stake cap has been reached. Try again after the UTC day resets.")
            state["currency"] = account["currency"]
            state["running"] = True
            state["status"] = "running"
            state["last_error"] = None
    except (psycopg.Error, OSError, RuntimeError):
        raise HTTPException(503, "The demo bot could not be started.") from None
    return JSONResponse(_public_state(state), headers={"Cache-Control": "no-store"})


@router.post("/api/bot/stop", include_in_schema=False)
@router.post("/api/deriv/demo-bot/stop")
async def stop_demo_bot(payload: DemoBotRequest, authorization: str = Header(default="")):
    connection = _deriv_connection(authorization)
    await _demo_account(connection["access_token"], payload.account_id)
    try:
        with _locked_state(payload.account_id, create=True) as state:
            state["running"] = False
            if state["pending_trade"]:
                state["status"] = "needs_review"
                state["last_error"] = "A trade may still be completing. Check Deriv before restarting."
            else:
                state["status"] = "stopped"
    except (psycopg.Error, OSError, RuntimeError):
        raise HTTPException(503, "The demo bot could not be stopped.") from None
    return JSONResponse(_public_state(state), headers={"Cache-Control": "no-store"})


@router.post("/api/deriv/demo-bot/resolve")
async def resolve_demo_bot(payload: DemoBotResolveRequest, authorization: str = Header(default="")):
    if not payload.confirmed_account_review:
        raise HTTPException(400, "Confirm that you checked the Deriv demo account.")
    connection = _deriv_connection(authorization)
    await _demo_account(connection["access_token"], payload.account_id)
    try:
        with _locked_state(payload.account_id, create=True) as state:
            if state["status"] != "needs_review":
                raise HTTPException(409, "There is no uncertain demo trade to resolve.")
            pending = state["pending_trade"]
            if pending and pending.get("stage") == "buy":
                state["active_until"] = max(
                    state["active_until"],
                    int(pending["created_at"]) + DURATION_MINUTES * 60 + 60,
                )
                state["last_trade"] = {
                    "contract_id": "unconfirmed",
                    "side": pending["side"],
                    "stake": str(STAKE),
                    "created_at": datetime.fromtimestamp(
                        pending["created_at"], timezone.utc
                    ).isoformat(),
                    "status": "outcome unconfirmed",
                }
            state["pending_trade"] = None
            state["running"] = False
            state["status"] = "stopped"
            state["last_error"] = None
    except (psycopg.Error, OSError, RuntimeError):
        raise HTTPException(503, "Demo bot state could not be resolved.") from None
    return JSONResponse(_public_state(state), headers={"Cache-Control": "no-store"})


@router.post("/api/deriv/demo-bot/cycle")
async def cycle_demo_bot(payload: DemoBotRequest, authorization: str = Header(default="")):
    connection = _deriv_connection(authorization)
    account = await _demo_account(connection["access_token"], payload.account_id)
    try:
        initial = _load_state(payload.account_id)
        if not initial["running"]:
            return JSONResponse(_public_state(initial), headers={"Cache-Control": "no-store"})
        if initial["pending_trade"]:
            pending_at = initial["pending_trade"].get("created_at", 0)
            if int(time.time()) - pending_at > 120:
                with _locked_state(payload.account_id) as state:
                    state["running"] = False
                    if state["pending_trade"] and state["pending_trade"].get("stage") == "proposal":
                        _release_proposal_stake(state)
                        state["status"] = "feed_error"
                        state["last_error"] = "The demo proposal did not complete. The bot was paused."
                    else:
                        state["status"] = "needs_review"
                        state["last_error"] = "A trade result is uncertain. Check Deriv before restarting."
                return JSONResponse(_public_state(state), headers={"Cache-Control": "no-store"})
            return JSONResponse(_public_state(initial), headers={"Cache-Control": "no-store"})
        ws_url = await _websocket_url(connection["access_token"], payload.account_id)
        async with websockets.connect(ws_url, open_timeout=10, close_timeout=3, max_size=65536) as socket:
            candles_response = await _ws_request(
                socket,
                {
                    "ticks_history": SYMBOL,
                    "end": "latest",
                    "count": 100,
                    "style": "candles",
                    "granularity": GRANULARITY,
                },
                10,
            )
            candle_data = candles_response.get("candles")
            candles = parse_candles(
                {"msg_type": "candles", "candles": candle_data,
                 "echo_req": {"ticks_history": SYMBOL}},
                SYMBOL,
            )["candles"]
            now = int(time.time())
            completed = [item for item in candles if item["epoch"] + GRANULARITY <= now]
            if len(completed) < 23:
                raise DemoBotProviderError("Deriv has not returned enough completed candles.")
            latest = completed[-1]
            if now - (latest["epoch"] + GRANULARITY) > MAX_CANDLE_AGE:
                with _locked_state(payload.account_id) as state:
                    state["last_cycle_at"] = datetime.now(timezone.utc).isoformat()
                    state["status"] = "waiting_for_market"
                return JSONResponse(_public_state(state), headers={"Cache-Control": "no-store"})
            side = ema_signal([float(item["close"]) for item in completed[-23:]])
            state, reserved = _reserve_signal(
                payload.account_id,
                side=side,
                candle_epoch=latest["epoch"],
                now=now,
            )
            if not reserved:
                return JSONResponse(_public_state(state), headers={"Cache-Control": "no-store"})
            try:
                contract_id = await _execute_trade(
                    socket, {"currency": account["currency"]}, side, payload.account_id
                )
            except (websockets.WebSocketException, OSError, asyncio.TimeoutError,
                    DemoBotProviderError, ValueError, KeyError, TypeError):
                with _locked_state(payload.account_id) as state:
                    pending = state["pending_trade"] or {}
                    uncertain = pending.get("stage") == "buy"
                state = _fail_trade(payload.account_id, uncertain=uncertain)
                return JSONResponse(
                    _public_state(state),
                    status_code=502,
                    headers={"Cache-Control": "no-store"},
                )
            state = _finish_trade(payload.account_id, contract_id)
    except HTTPException:
        raise
    except (psycopg.Error, OSError, RuntimeError):
        raise HTTPException(503, "The demo bot is temporarily unavailable.") from None
    except (httpx.HTTPError, websockets.WebSocketException, asyncio.TimeoutError,
            DerivMarketDataError, DemoBotProviderError, ValueError, KeyError, TypeError):
        try:
            with _locked_state(payload.account_id) as state:
                state["running"] = False
                state["last_cycle_at"] = datetime.now(timezone.utc).isoformat()
                state["status"] = "feed_error"
                state["last_error"] = "Deriv data was unavailable. The bot was paused; review status before restarting."
        except (psycopg.Error, OSError, RuntimeError):
            raise HTTPException(503, "The demo bot is temporarily unavailable.") from None
        return JSONResponse(
            _public_state(state),
            status_code=502,
            headers={"Cache-Control": "no-store"},
        )
    return JSONResponse(_public_state(state), headers={"Cache-Control": "no-store"})
