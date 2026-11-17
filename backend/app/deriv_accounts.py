"""Encrypted Deriv connections and explicitly labelled demo/real account balances."""
import json
import re
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

import httpx
import psycopg
from cryptography.fernet import InvalidToken
from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import JSONResponse

router = APIRouter()
COLLECTION = 'deriv_oauth_connections'


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


@router.post('/api/deriv/session/logout')
def logout_deriv_session(authorization: str = Header(default='')):
    from app.deriv_signin import revoke_session
    try:
        revoke_session(authorization)
    except (psycopg.Error,OSError,RuntimeError):
        raise HTTPException(503,'Sign-out is temporarily unavailable. Please retry.') from None
    return JSONResponse({'revoked':True},headers={'Cache-Control':'no-store'})
