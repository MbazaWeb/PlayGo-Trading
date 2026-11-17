"""Serverless-safe Deriv OAuth 2.0 PKCE connection, with encrypted cookies."""
import base64
import hashlib
import json
import os
import re
import secrets
import time
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx
import psycopg
from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from pydantic import BaseModel, Field

router = APIRouter()
FLOW_COOKIE = '__Host-playgo-deriv-flow'
CONNECTION_COOKIE = '__Secure-playgo-deriv'
HEADERS = {'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer',
           'Content-Security-Policy': "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'",
           'X-Content-Type-Options': 'nosniff'}


def cipher():
    try:
        return Fernet(os.environ['DERIV_OAUTH_ENCRYPTION_KEY'].encode())
    except (KeyError, ValueError, TypeError):
        raise HTTPException(503, 'Deriv OAuth encryption is not configured') from None


def config():
    client_id = os.getenv('DERIV_OAUTH_CLIENT_ID', '').strip()
    redirect_uri = os.getenv('DERIV_OAUTH_REDIRECT_URI', '').strip()
    url = urlsplit(redirect_uri)
    if not client_id or url.scheme != 'https' or not url.netloc or url.query or url.fragment or url.username or url.password:
        raise HTTPException(503, 'Configure DERIV_OAUTH_CLIENT_ID and the HTTPS DERIV_OAUTH_REDIRECT_URI')
    return client_id, redirect_uri


def page(title, message, status=200):
    # Only fixed application text is passed here; no provider or query-string text.
    return HTMLResponse('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>PlayGo Deriv connection</title><style>body{font:16px system-ui;background:#101b29;color:#e9f3ff;max-width:540px;margin:10vh auto;padding:24px;line-height:1.7}input,button{display:block;box-sizing:border-box;width:100%;padding:12px;margin:8px 0 20px;border-radius:8px;border:1px solid #43546b}button{background:#82dfbd;color:#102c24;font-weight:700}small{color:#a8bbcf}</style><h1>'+title+'</h1>'+message+'</html>', status_code=status, headers=HEADERS)


@router.get('/deriv/connect', response_class=HTMLResponse)
def connect_page():
    return page('Connect Deriv', '<p>Sign in with your PlayGo owner credentials to start the Deriv connection. Deriv will ask you to sign in and consent on its own website.</p><form method="post" action="/api/deriv/oauth/start"><label>PlayGo username<input name="username" required autocomplete="username"></label><label>PlayGo password<input name="password" type="password" required autocomplete="current-password"></label><button>Continue to Deriv</button></form><small>PlayGo can place demo Options contracts only when you explicitly start the demo bot. Real-account trading and transfers are disabled.</small>')


@router.post('/api/deriv/oauth/start')
async def start(request: Request):
    from app.postgres_api import Credentials, login
    client_id, redirect_uri = config()
    parsed = urlsplit(redirect_uri)
    expected_origin = parsed.scheme + '://' + parsed.netloc
    if request.headers.get('origin') != expected_origin:
        raise HTTPException(403, 'Start the connection from the PlayGo connection page')
    if not request.headers.get('content-type', '').startswith('application/x-www-form-urlencoded'):
        raise HTTPException(415, 'Expected a form submission')
    raw = await request.body()
    if len(raw) > 2048:
        raise HTTPException(400, 'Invalid credentials form')
    fields = parse_qs(raw.decode('utf-8', errors='replace'))
    session = login(Credentials(username=fields.get('username', [''])[0], password=fields.get('password', [''])[0]))
    verifier = secrets.token_urlsafe(48)
    state = secrets.token_urlsafe(32)
    flow = {'state': state, 'verifier': verifier, 'owner_session': session['access_token'], 'redirect_uri': redirect_uri, 'client_id': client_id}
    return authorize(flow)


def authorize(flow):
    challenge = base64.urlsafe_b64encode(hashlib.sha256(flow['verifier'].encode()).digest()).rstrip(b'=').decode()
    params = {'response_type': 'code', 'client_id': flow['client_id'], 'redirect_uri': flow['redirect_uri'],
              'scope': 'trade', 'state': flow['state'], 'code_challenge': challenge, 'code_challenge_method': 'S256'}
    response = RedirectResponse('https://auth.deriv.com/oauth2/auth?' + urlencode(params), status_code=303, headers=HEADERS)
    response.set_cookie(FLOW_COOKIE, cipher().encrypt(json.dumps(flow).encode()).decode(), max_age=600, secure=True, httponly=True, samesite='lax', path='/')
    return response


@router.get('/api/deriv/oauth/signin')
def signin(origin: str = 'https://playgo-ai-trading.vercel.app', handoff_id: str = '', handoff_challenge: str = ''):
    client_id, redirect_uri = config()
    allowed = {value.strip() for value in os.getenv('CORS_ORIGINS', 'https://playgo-ai-trading.vercel.app').split(',')}
    if origin not in allowed:
        raise HTTPException(400, 'Unsupported PlayGo origin')
    if bool(handoff_id) != bool(handoff_challenge) or (handoff_id and (not re.fullmatch(r'[A-Za-z0-9_-]{43}',handoff_id) or not re.fullmatch(r'[A-Za-z0-9_-]{43}',handoff_challenge))):
        raise HTTPException(400, 'Invalid sign-in handoff')
    return authorize({'mode': 'signin', 'frontend_origin': origin, 'client_id': client_id,
                      'handoff_id': handoff_id, 'handoff_challenge': handoff_challenge,
                      'redirect_uri': redirect_uri, 'state': secrets.token_urlsafe(32),
                      'verifier': secrets.token_urlsafe(48)})


def signin_complete(token, origin):
    nonce = secrets.token_urlsafe(24)
    payload = json.dumps({'type': 'playgo-deriv-signin', 'session_token': token}).replace('<', '\u003c')
    target = json.dumps(origin).replace('<', '\u003c')
    response = page('Signed in with Deriv', '<p>Returning to PlayGo. If this window stays open, return to PlayGo and start sign-in again.</p>'
                    + '<script nonce="' + nonce + '">if(window.opener){window.opener.postMessage(' + payload + ',' + target + ');window.close();}</script>')
    response.headers['Content-Security-Policy'] = HEADERS['Content-Security-Policy'] + "; script-src 'nonce-" + nonce + "'"
    return response


@router.get('/api/deriv/oauth/callback', response_class=HTMLResponse)
async def callback(request: Request):
    from app.postgres_api import owner
    encoded = request.cookies.get(FLOW_COOKIE)
    if not encoded:
        return page('Connection not started', '<p>Open <a href="/deriv/connect">Connect Deriv</a> to start a new connection. This is the registered OAuth redirect URL.</p>', 400)
    try:
        flow = json.loads(cipher().decrypt(encoded.encode(), ttl=600))
        returned_state = request.query_params.get('state', '')
        if not returned_state or not secrets.compare_digest(returned_state, flow['state']):
            raise ValueError('state')
        owner_id = None if flow.get('mode') == 'signin' else owner('Bearer ' + flow['owner_session'])
        client_id, redirect_uri = config()
        if flow['client_id'] != client_id or flow['redirect_uri'] != redirect_uri:
            raise ValueError('configuration changed')
    except (InvalidToken, ValueError, KeyError, TypeError):
        response = page('Connection expired', '<p>The connection request is invalid or expired. <a href="/deriv/connect">Start again</a>.</p>', 400)
        response.delete_cookie(FLOW_COOKIE, secure=True, httponly=True, samesite='lax', path='/')
        return response
    if request.query_params.get('error') or not request.query_params.get('code'):
        response = page('Connection cancelled', '<p>Deriv did not authorize the connection. You can <a href="/deriv/connect">try again</a>.</p>', 400)
    else:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                result = await client.post('https://auth.deriv.com/oauth2/token', data={
                    'grant_type': 'authorization_code', 'client_id': client_id, 'redirect_uri': redirect_uri,
                    'code': request.query_params['code'], 'code_verifier': flow['verifier']})
                result.raise_for_status()
                token = result.json()
            access_token, expiry = token['access_token'], token['expires_in']
            if not isinstance(access_token, str) or not access_token or len(access_token)>2048 or type(expiry) is not int or expiry <= 0 or token.get('token_type','').lower() != 'bearer':
                raise ValueError('invalid token response')
            lifetime = min(expiry, 8*60*60)
            connection = {'access_token': access_token, 'owner_id': owner_id, 'expires_at': int(time.time())+lifetime, 'client_id': client_id}
            if flow.get('mode') == 'signin':
                from app.deriv_signin import create_session, create_handoff
                session_token = create_session(connection)
                if flow.get('handoff_id'):
                    create_handoff(flow['handoff_id'], flow['handoff_challenge'], flow['frontend_origin'], session_token)
                    nonce = secrets.token_urlsafe(24)
                    response = page('Signed in with Deriv', '<p>Sign-in complete. Return to PlayGo; this window can be closed.</p><script nonce="' + nonce + '">window.close();</script>')
                    response.headers['Content-Security-Policy'] = HEADERS['Content-Security-Policy'] + "; script-src 'nonce-" + nonce + "'"
                else:
                    response = signin_complete(session_token, flow['frontend_origin'])
            else:
                from app.deriv_accounts import save_connection
                save_connection(owner_id, connection)
                response = page('Deriv connected', '<p>Your authorization was received securely. Your demo and real Options account balances are available in PlayGo.</p><p>The bot can place demo Options contracts only after you explicitly start it. Real-account trading and transfers remain disabled. <a href="https://playgo-ai-trading.vercel.app/">Return to PlayGo</a>.</p>')
                response.set_cookie(CONNECTION_COOKIE, cipher().encrypt(json.dumps(connection).encode()).decode(), max_age=lifetime, secure=True, httponly=True, samesite='lax', path='/api/deriv')
        except (httpx.HTTPError, psycopg.Error, OSError, RuntimeError, ValueError, KeyError, TypeError):
            response = page('Connection unsuccessful', '<p>Deriv could not complete authorization. Check the registered client ID and exact redirect URL, then <a href="/deriv/connect">try again</a>.</p>', 502)
    response.delete_cookie(FLOW_COOKIE, secure=True, httponly=True, samesite='lax', path='/')
    return response


class SigninCompletion(BaseModel):
    handoff_id: str = Field(min_length=43,max_length=43,pattern=r'^[A-Za-z0-9_-]+$')
    verifier: str = Field(min_length=43,max_length=128,pattern=r'^[A-Za-z0-9._~-]+$')


@router.post('/api/deriv/oauth/complete')
def complete_signin(payload: SigninCompletion, request: Request):
    from app.deriv_signin import consume_handoff
    origin=request.headers.get('origin','')
    allowed={value.strip() for value in os.getenv('CORS_ORIGINS','https://playgo-ai-trading.vercel.app').split(',')}
    if origin not in allowed:
        raise HTTPException(403,'Unsupported PlayGo origin')
    try:
        token=consume_handoff(payload.handoff_id,payload.verifier,origin)
    except (psycopg.Error,OSError,RuntimeError):
        raise HTTPException(503,'Sign-in completion is temporarily unavailable. Please sign in again.') from None
    if token is None:
        return JSONResponse({'pending':True},status_code=202,headers={'Cache-Control':'no-store'})
    return JSONResponse({'session_token':token},headers={'Cache-Control':'no-store'})
