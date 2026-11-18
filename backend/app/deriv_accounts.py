"""Encrypted Deriv connections and explicitly labelled demo/real account balances."""
import asyncio
import json
import re
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from urllib.parse import parse_qs, quote, urlsplit

import httpx
import psycopg
import websockets
from cryptography.fernet import InvalidToken
from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import JSONResponse

router = APIRouter()
COLLECTION = 'deriv_oauth_connections'
API_BASE = 'https://api.derivws.com'
MAX_PROFIT_TRANSACTIONS = 500


def save_connection(owner_id, connection):
    from app.postgres_api import connect
    from app.deriv_oauth import cipher
    encrypted = cipher().encrypt(json.dumps(connection).encode()).decode()
    with connect() as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                cur.execute('''insert into playgo_private.documents
                    (collection_name,document_id,body,revision) values (%s,%s,%s::jsonb,0)
                    on conflict (collection_name,document_id) do update
                    set body=excluded.body,revision=playgo_private.documents.revision+1''',
                    (COLLECTION, owner_id, json.dumps({'encrypted_connection': encrypted})))


def load_connection(owner_id):
    from app.postgres_api import connect
    from app.deriv_oauth import cipher, config
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute('select body from playgo_private.documents where collection_name=%s and document_id=%s', (COLLECTION, owner_id))
            row = cur.fetchone()
    if row is None:
        return None
    try:
        body = row[0] if isinstance(row[0],dict) else json.loads(row[0])
        connection = json.loads(cipher().decrypt(body['encrypted_connection'].encode(),ttl=8*60*60))
        if connection['owner_id'] != owner_id or connection['expires_at'] <= time.time() or connection.get('client_id') != config()[0]:
            return None
        return connection
    except (InvalidToken,KeyError,TypeError,ValueError):
        return None


def parse_accounts(payload):
    if not isinstance(payload,dict) or not isinstance(payload.get('data'),list):
        raise ValueError('Invalid account list')
    accounts=[]
    for item in payload['data']:
        if not isinstance(item,dict):
            raise ValueError('Invalid account')
        if item.get('account_type') not in ('real','demo'):
            continue
        account_id, currency = item.get('account_id'), item.get('currency')
        if not isinstance(account_id,str) or not 1 <= len(account_id) <= 128 or not isinstance(currency,str) or not re.fullmatch(r'[A-Z0-9]{2,12}',currency):
            raise ValueError('Invalid account identity')
        raw = item.get('balance')
        if raw is None:
            balance = None
        else:
            if isinstance(raw,bool):
                raise ValueError('Invalid balance')
            try:
                value = Decimal(str(raw))
            except InvalidOperation:
                raise ValueError('Invalid balance') from None
            if not value.is_finite() or abs(value) > Decimal('1e18'):
                raise ValueError('Invalid balance')
            balance = str(value)
        accounts.append({'account_id':account_id,'currency':currency,'balance':balance,'account_type':item['account_type']})
    return accounts


@router.get('/api/deriv/accounts')
async def real_accounts(authorization: str = Header(default='')):
    from app.postgres_api import owner
    try:
        if authorization.startswith('Bearer deriv_'):
            from app.deriv_signin import read_session
            connection = read_session(authorization)
        else:
            connection = load_connection(owner(authorization))
    except (psycopg.Error,OSError,RuntimeError):
        raise HTTPException(503,'Deriv connection storage is temporarily unavailable') from None
    common={'source':'DERIV','execution':'DISABLED'}
    if not connection:
        return JSONResponse({**common,'connected':False,'reason':'CONNECT_REQUIRED','accounts':[]},headers={'Cache-Control':'no-store'})
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response=await client.get('https://api.derivws.com/trading/v1/options/accounts',headers={'Authorization':'Bearer '+connection['access_token']})
        if response.status_code in (401,403):
            return JSONResponse({**common,'connected':False,'reason':'RECONNECT_REQUIRED','accounts':[]},headers={'Cache-Control':'no-store'})
        response.raise_for_status()
        accounts=parse_accounts(response.json())
    except (httpx.HTTPError,ValueError,KeyError,TypeError):
        raise HTTPException(502,'Deriv balances are currently unavailable. Please refresh to retry.') from None
    return JSONResponse({**common,'connected':True,'accounts':accounts,'observed_at':datetime.now(timezone.utc).isoformat()},headers={'Cache-Control':'no-store'})


def _money(value, field):
    if isinstance(value, bool):
        raise ValueError(f'Invalid {field}')
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f'Invalid {field}') from None
    if not amount.is_finite() or abs(amount) > Decimal('1e18'):
        raise ValueError(f'Invalid {field}')
    return amount


async def _verified_account(connection, account_id):
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(
                API_BASE + '/trading/v1/options/accounts',
                headers={'Authorization': 'Bearer ' + connection['access_token']},
            )
        if response.status_code in (401, 403):
            raise HTTPException(401, 'Deriv authorization expired. Please sign in again.')
        response.raise_for_status()
        accounts = parse_accounts(response.json())
    except HTTPException:
        raise
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        raise HTTPException(502, 'Deriv account information is currently unavailable.') from None
    account = next((item for item in accounts if item['account_id'] == account_id), None)
    if account is None:
        raise HTTPException(404, 'The requested account is not available in this Deriv session.')
    return account


async def _options_websocket_url(connection, account):
    url = API_BASE + '/trading/v1/options/accounts/' + quote(account['account_id'], safe='') + '/otp'
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                url, headers={'Authorization': 'Bearer ' + connection['access_token']}
            )
        if response.status_code in (401, 403):
            raise HTTPException(401, 'Deriv authorization expired. Please sign in again.')
        response.raise_for_status()
        payload = response.json()
    except HTTPException:
        raise
    except (httpx.HTTPError, ValueError, TypeError):
        raise HTTPException(502, 'Deriv account data is currently unavailable.') from None

    ws_url = payload.get('data', {}).get('url') if isinstance(payload, dict) else None
    if not isinstance(ws_url, str):
        raise HTTPException(502, 'Deriv did not return an account data connection.')
    try:
        parsed = urlsplit(ws_url)
        port = parsed.port
    except ValueError:
        raise HTTPException(502, 'Deriv returned an invalid account data connection.') from None
    otp = parse_qs(parsed.query).get('otp', [])
    expected_path = '/trading/v1/options/ws/' + account['account_type']
    if (
        parsed.scheme != 'wss'
        or parsed.hostname != 'api.derivws.com'
        or port not in (None, 443)
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path != expected_path
        or len(otp) != 1
        or not otp[0]
        or parsed.fragment
    ):
        raise HTTPException(502, 'Deriv returned an invalid account data connection.')
    return ws_url


async def _account_ws_request(socket, request, request_id):
    await socket.send(json.dumps({**request, 'req_id': request_id}))
    for _ in range(32):
        try:
            message = json.loads(await asyncio.wait_for(socket.recv(), timeout=12))
        except (asyncio.TimeoutError, json.JSONDecodeError):
            raise HTTPException(502, 'Timed out waiting for Deriv account data.') from None
        if not isinstance(message, dict):
            continue
        echoed = message.get('req_id')
        if echoed is None and isinstance(message.get('echo_req'), dict):
            echoed = message['echo_req'].get('req_id')
        if echoed != request_id:
            continue
        if message.get('error'):
            raise HTTPException(502, 'Deriv rejected an account data request.')
        return message
    raise HTTPException(502, 'Deriv did not return the expected account data.')


def _contract_direction(contract_type):
    if not isinstance(contract_type, str):
        return 'other'
    kind = contract_type.upper()
    if kind in {'CALL', 'CALLE', 'HIGHER', 'MULTUP', 'VANILLALONGCALL', 'RESETCALL'}:
        return 'up'
    if kind in {'PUT', 'PUTE', 'LOWER', 'MULTDOWN', 'VANILLALONGPUT', 'RESETPUT'}:
        return 'down'
    return 'other'


def _performance_response(account, open_contracts, transactions):
    open_positions = []
    unrealized_total = Decimal('0')
    exposures = {}
    for row in open_contracts:
        contract_id = row.get('contract_id')
        symbol = row.get('underlying') or row.get('symbol') or row.get('underlying_symbol')
        contract_type = row.get('contract_type')
        if not isinstance(contract_id, (str, int)) or not isinstance(symbol, str):
            raise ValueError('Invalid open contract')
        profit = _money(row.get('profit'), 'open contract profit')
        stake = _money(row.get('buy_price'), 'open contract stake')
        direction = _contract_direction(contract_type)
        unrealized_total += profit
        open_positions.append({
            'contract_id': str(contract_id),
            'symbol': symbol,
            'contract_type': contract_type if isinstance(contract_type, str) else 'UNKNOWN',
            'direction': direction,
            'buy_price': str(stake),
            'profit': str(profit),
            'purchase_time': row.get('purchase_time'),
        })
        exposure = exposures.setdefault(symbol, {'symbol': symbol, 'up_stake': Decimal('0'), 'down_stake': Decimal('0'), 'other_stake': Decimal('0'), 'up_count': 0, 'down_count': 0, 'other_count': 0})
        exposure[direction + '_stake'] += stake
        exposure[direction + '_count'] += 1

    realized_total = Decimal('0')
    closed = []
    for row in transactions:
        if not isinstance(row, dict):
            raise ValueError('Invalid Deriv transaction')
        # A profit-table entry can have settled prices without a sell timestamp.
        if row.get('sell_price') is None and row.get('sell_time') is None:
            continue
        buy_price = _money(row.get('buy_price'), 'closed contract buy price')
        sell_price = _money(row.get('sell_price'), 'closed contract sell price')
        profit = sell_price - buy_price
        realized_total += profit
        closed.append({
            'contract_id': str(row.get('contract_id') or row.get('transaction_id') or ''),
            'symbol': row.get('underlying') or row.get('symbol') or row.get('underlying_symbol') or 'Unknown',
            'contract_type': row.get('contract_type') if isinstance(row.get('contract_type'), str) else 'UNKNOWN',
            'buy_price': str(buy_price),
            'sell_price': str(sell_price),
            'profit': str(profit),
            'sell_time': row.get('sell_time'),
        })

    public_exposures = []
    for exposure in exposures.values():
        exposure['opposing_stake'] = min(exposure['up_stake'], exposure['down_stake'])
        public_exposures.append({
            key: str(value) if isinstance(value, Decimal) else value
            for key, value in exposure.items()
        })
    return {
        'source': 'DERIV',
        'execution': 'DISABLED',
        'account_id': account['account_id'],
        'account_type': account['account_type'],
        'currency': account['currency'],
        'open_positions': open_positions,
        'unrealized_pnl': str(unrealized_total),
        'realized_pnl': str(realized_total),
        'realized_transaction_count': len(closed),
        'realized_window': f'Up to the {MAX_PROFIT_TRANSACTIONS} most recent Deriv transactions',
        'realized_may_be_truncated': len(transactions) >= MAX_PROFIT_TRANSACTIONS,
        'recent_closed': closed,
        'opposing_exposure': public_exposures,
        'exposure_note': 'Opposing positions are informational only and are not guaranteed to offset losses.',
        'observed_at': datetime.now(timezone.utc).isoformat(),
    }


@router.get('/api/deriv/accounts/{account_id}/performance')
async def account_performance(account_id: str, authorization: str = Header(default='')):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', account_id):
        raise HTTPException(400, 'Invalid Deriv account id.')
    try:
        if authorization.startswith('Bearer deriv_'):
            from app.deriv_signin import read_session
            connection = read_session(authorization)
        else:
            from app.postgres_api import owner
            connection = load_connection(owner(authorization))
    except HTTPException:
        raise
    except (psycopg.Error, OSError, RuntimeError):
        raise HTTPException(503, 'Deriv connection storage is temporarily unavailable.') from None
    if not connection:
        raise HTTPException(401, 'Sign in with Deriv to view account performance.')

    account = await _verified_account(connection, account_id)
    ws_url = await _options_websocket_url(connection, account)
    try:
        async with websockets.connect(
            ws_url, open_timeout=10, close_timeout=3, max_size=262144
        ) as socket:
            portfolio_response = await _account_ws_request(
                socket, {'portfolio': 1}, 1
            )
            portfolio = portfolio_response.get('portfolio')
            contracts = portfolio.get('contracts') if isinstance(portfolio, dict) else None
            if contracts is None and isinstance(portfolio, dict) and portfolio.get('count') == 0:
                contracts = []
            if not isinstance(contracts, list) or len(contracts) > 100:
                raise HTTPException(502, 'Deriv returned invalid open position data.')
            open_contracts = []
            for index, item in enumerate(contracts, start=2):
                if not isinstance(item, dict) or item.get('contract_id') is None:
                    raise HTTPException(502, 'Deriv returned invalid open position data.')
                contract_response = await _account_ws_request(
                    socket,
                    {'proposal_open_contract': 1, 'contract_id': item['contract_id']},
                    index,
                )
                contract = contract_response.get('proposal_open_contract')
                if not isinstance(contract, dict):
                    raise HTTPException(502, 'Deriv returned invalid open position data.')
                returned_id = contract.get('contract_id')
                if returned_id is not None and str(returned_id) != str(item['contract_id']):
                    raise HTTPException(502, 'Deriv returned mismatched open position data.')
                if contract.get('is_sold') in (1, True, '1'):
                    continue
                open_contracts.append({**item, **contract})

            profit_response = await _account_ws_request(
                socket,
                {'profit_table': 1, 'description': 1, 'limit': MAX_PROFIT_TRANSACTIONS, 'offset': 0, 'sort': 'DESC'},
                102,
            )
            profit_table = profit_response.get('profit_table')
            transactions = profit_table.get('transactions') if isinstance(profit_table, dict) else None
            if not isinstance(transactions, list):
                raise HTTPException(502, 'Deriv returned invalid closed position data.')
            result = _performance_response(account, open_contracts, transactions)
    except HTTPException:
        raise
    except (websockets.exceptions.WebSocketException, OSError, asyncio.TimeoutError):
        raise HTTPException(502, 'Deriv account performance is currently unavailable.') from None
    except (ValueError, TypeError, InvalidOperation):
        raise HTTPException(502, 'Deriv returned invalid account performance data.') from None
    return JSONResponse(result, headers={'Cache-Control': 'no-store'})


@router.post('/api/deriv/session/logout')
def logout_deriv_session(authorization: str = Header(default='')):
    from app.deriv_signin import revoke_session
    try:
        revoke_session(authorization)
    except (psycopg.Error,OSError,RuntimeError):
        raise HTTPException(503,'Sign-out is temporarily unavailable. Please retry.') from None
    return JSONResponse({'revoked':True},headers={'Cache-Control':'no-store'})
