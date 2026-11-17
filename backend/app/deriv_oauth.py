"""Serverless-safe Deriv OAuth 2.0 PKCE connection, with encrypted cookies."""
import base64
import hashlib
import json
import os
import secrets
import time
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx
from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

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
    return page('Connect Deriv', '<p>Sign in with your PlayGo owner credentials to start the Deriv connection. Deriv will ask you to sign in and consent on its own website.</p><form method="post" action="/api/deriv/oauth/start"><label>PlayGo username<input name="username" required autocomplete="username"></label><label>PlayGo password<input name="password" type="password" required autocomplete="current-password"></label><button>Continue to Deriv</button></form><small>This connection does not enable live trading or transfer funds.</small>')


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
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
    params = {'response_type': 'code', 'client_id': client_id, 'redirect_uri': redirect_uri,
              'scope': 'application_read', 'state': state, 'code_challenge': challenge, 'code_challenge_method': 'S256'}
    response = RedirectResponse('https://auth.deriv.com/oauth2/auth?' + urlencode(params), status_code=303, headers=HEADERS)
    response.set_cookie(FLOW_COOKIE, cipher().encrypt(json.dumps(flow).encode()).decode(), max_age=600, secure=True, httponly=True, samesite='lax', path='/')
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
        owner_id = owner('Bearer ' + flow['owner_session'])
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
            connection = {'access_token': access_token, 'owner_id': owner_id, 'expires_at': int(time.time())+lifetime}
            response = page('Deriv connected', '<p>Your authorization was received securely. The encrypted connection lasts up to eight hours in this browser.</p><p>Live trading and money transfers remain disabled. This initial connection requests application-read access only; it does not connect your real orders or balance.</p>')
            response.set_cookie(CONNECTION_COOKIE, cipher().encrypt(json.dumps(connection).encode()).decode(), max_age=lifetime, secure=True, httponly=True, samesite='lax', path='/api/deriv')
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            response = page('Connection unsuccessful', '<p>Deriv could not complete authorization. Check the registered client ID and exact redirect URL, then <a href="/deriv/connect">try again</a>.</p>', 502)
    response.delete_cookie(FLOW_COOKIE, secure=True, httponly=True, samesite='lax', path='/')
    return response
