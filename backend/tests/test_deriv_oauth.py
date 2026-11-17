"""OAuth PKCE contracts. No real authorization, credentials, or payment calls."""
import json
import os
import unittest
from urllib.parse import parse_qs,urlsplit
from unittest.mock import AsyncMock,patch
from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app import deriv_oauth as oauth
from app import postgres_api

class OAuthTests(unittest.TestCase):
    def setUp(self):
        self.env=patch.dict(os.environ,{'DERIV_OAUTH_CLIENT_ID':'test-client','DERIV_OAUTH_REDIRECT_URI':'https://api.example/api/deriv/oauth/callback','DERIV_OAUTH_ENCRYPTION_KEY':Fernet.generate_key().decode()})
        self.env.start();self.addCleanup(self.env.stop)
        app=FastAPI();app.include_router(oauth.router)
        self.client=TestClient(app,base_url='https://api.example',follow_redirects=False)

    def begin(self):
        with patch.object(postgres_api,'login',return_value={'access_token':'owner-session'}):
            response=self.client.post('/api/deriv/oauth/start',data={'username':'owner','password':'test-only'},headers={'origin':'https://api.example'})
        return response

    def test_entrypoint_has_no_mongo_import(self):
        import subprocess,sys
        code="import sys; import app.index; assert 'app.main' not in sys.modules; assert 'pymongo' not in sys.modules; assert 'app.ledger' not in sys.modules"
        from pathlib import Path
        subprocess.run([sys.executable,'-c',code],check=True,cwd=Path(__file__).resolve().parents[1])

    def test_connection_page(self):
        r=self.client.get('/deriv/connect');self.assertEqual(r.status_code,200)
        self.assertEqual(r.headers['cache-control'],'no-store')

    def test_start_is_pkce_and_cookie_encrypted(self):
        r=self.begin();self.assertEqual(r.status_code,303)
        params=parse_qs(urlsplit(r.headers['location']).query)
        self.assertEqual(params['code_challenge_method'],['S256'])
        self.assertEqual(params['scope'],['trade'])
        self.assertNotIn('owner-session',r.headers['set-cookie'])
        self.assertIn('HttpOnly',r.headers['set-cookie']);self.assertIn('Secure',r.headers['set-cookie'])

    def test_start_rejects_foreign_origin(self):
        r=self.client.post('/api/deriv/oauth/start',data={'username':'owner','password':'x'},headers={'origin':'https://evil.example'})
        self.assertEqual(r.status_code,403)

    def test_missing_flow_is_clean_error(self):
        r=self.client.get('/api/deriv/oauth/callback');self.assertEqual(r.status_code,400)
        self.assertIn('Connection not started',r.text)

    def test_state_mismatch_never_exchanges_token(self):
        self.begin()
        with patch.object(oauth.httpx,'AsyncClient') as client:
            r=self.client.get('/api/deriv/oauth/callback?code=test-code&state=wrong')
            self.assertEqual(r.status_code,400);client.assert_not_called()

    def test_success_has_no_plaintext_token(self):
        start=self.begin();state=parse_qs(urlsplit(start.headers['location']).query)['state'][0]
        result=unittest.mock.Mock();result.json.return_value={'access_token':'test-private-token','expires_in':3600,'token_type':'Bearer'}
        client=AsyncMock();client.post.return_value=result
        with patch('app.deriv_accounts.save_connection') as save,patch.object(postgres_api,'owner',return_value='owner-id'),patch.object(oauth.httpx,'AsyncClient') as cls:
            cls.return_value.__aenter__.return_value=client
            r=self.client.get('/api/deriv/oauth/callback',params={'code':'test-code','state':state})
        self.assertEqual(r.status_code,200);self.assertIn('Deriv connected',r.text)
        self.assertNotIn('test-private-token',r.text+r.headers['set-cookie'])
        self.assertNotIn('test-code',r.text)
        token_cookie=self.client.cookies.get(oauth.CONNECTION_COOKIE)
        data=json.loads(oauth.cipher().decrypt(token_cookie.encode()))
        self.assertEqual(data['owner_id'],'owner-id')
        save.assert_called_once()
        self.assertIsNone(self.client.cookies.get(oauth.FLOW_COOKIE))

    def test_expired_flow_rejected(self):
        self.begin()
        with patch.object(Fernet,'decrypt',side_effect=oauth.InvalidToken):
            self.assertEqual(self.client.get('/api/deriv/oauth/callback?code=x&state=x').status_code,400)

    def test_direct_signin_needs_no_owner_credentials(self):
        with patch.dict(os.environ,{'CORS_ORIGINS':'https://playgo-ai-trading.vercel.app'}),patch.object(postgres_api,'login') as login:
            response=self.client.get('/api/deriv/oauth/signin?origin=https://playgo-ai-trading.vercel.app')
        self.assertEqual(response.status_code,303);login.assert_not_called()
        params=parse_qs(urlsplit(response.headers['location']).query)
        self.assertEqual(params['code_challenge_method'],['S256'])

    def test_direct_signin_rejects_foreign_origin(self):
        with patch.dict(os.environ,{'CORS_ORIGINS':'https://playgo-ai-trading.vercel.app'}):
            self.assertEqual(self.client.get('/api/deriv/oauth/signin?origin=https://attacker.example').status_code,400)

    def test_direct_callback_returns_app_session_only_to_expected_origin(self):
        origin='https://playgo-ai-trading.vercel.app'
        with patch.dict(os.environ,{'CORS_ORIGINS':origin}):
            start=self.client.get('/api/deriv/oauth/signin',params={'origin':origin})
        state=parse_qs(urlsplit(start.headers['location']).query)['state'][0]
        result=unittest.mock.Mock();result.json.return_value={'access_token':'deriv-provider-private-token','expires_in':3600,'token_type':'Bearer'}
        client=AsyncMock();client.post.return_value=result
        app_token='deriv_'+('a'*64)
        with patch('app.deriv_signin.create_session',return_value=app_token) as create,patch.object(postgres_api,'owner') as owner,patch.object(oauth.httpx,'AsyncClient') as cls:
            cls.return_value.__aenter__.return_value=client
            response=self.client.get('/api/deriv/oauth/callback',params={'code':'code','state':state})
        self.assertEqual(response.status_code,200);owner.assert_not_called();create.assert_called_once()
        self.assertIn('window.opener.postMessage',response.text);self.assertIn(origin,response.text)
        self.assertIn(app_token,response.text);self.assertNotIn('deriv-provider-private-token',response.text)
        self.assertIn("script-src 'nonce-",response.headers['Content-Security-Policy'])
        self.assertIsNone(self.client.cookies.get(oauth.FLOW_COOKIE))

    def test_popup_callback_saves_handoff_without_needing_opener(self):
        origin='https://playgo-ai-trading.vercel.app'
        handoff_id='h'*43
        challenge='c'*43
        with patch.dict(os.environ,{'CORS_ORIGINS':origin}):
            start=self.client.get('/api/deriv/oauth/signin',params={'origin':origin,'handoff_id':handoff_id,'handoff_challenge':challenge})
        state=parse_qs(urlsplit(start.headers['location']).query)['state'][0]
        result=unittest.mock.Mock();result.json.return_value={'access_token':'provider-secret','expires_in':3600,'token_type':'Bearer'}
        client=AsyncMock();client.post.return_value=result
        app_token='deriv_'+('a'*64)
        with patch('app.deriv_signin.create_session',return_value=app_token),patch('app.deriv_signin.create_handoff') as save_handoff,patch.object(postgres_api,'owner') as owner,patch.object(oauth.httpx,'AsyncClient') as cls:
            cls.return_value.__aenter__.return_value=client
            response=self.client.get('/api/deriv/oauth/callback',params={'code':'code','state':state})
        self.assertEqual(response.status_code,200);owner.assert_not_called()
        save_handoff.assert_called_once_with(handoff_id,challenge,origin,app_token)
        self.assertIn('window.close()',response.text)
        self.assertNotIn(app_token,response.text)
        self.assertNotIn('window.opener',response.text)
        self.assertIsNone(self.client.cookies.get(oauth.FLOW_COOKIE))

    def test_handoff_poll_returns_pending_until_callback_is_saved(self):
        origin='https://playgo-ai-trading.vercel.app'
        payload={'handoff_id':'h'*43,'verifier':'v'*43}
        with patch.dict(os.environ,{'CORS_ORIGINS':origin}),patch('app.deriv_signin.consume_handoff',return_value=None):
            pending=self.client.post('/api/deriv/oauth/complete',json=payload,headers={'origin':origin})
        self.assertEqual(pending.status_code,202)
        self.assertEqual(pending.json(),{'pending':True})
        self.assertEqual(pending.headers['cache-control'],'no-store')
        app_token='deriv_'+('a'*64)
        with patch.dict(os.environ,{'CORS_ORIGINS':origin}),patch('app.deriv_signin.consume_handoff',return_value=app_token):
            complete=self.client.post('/api/deriv/oauth/complete',json=payload,headers={'origin':origin})
        self.assertEqual(complete.status_code,200)
        self.assertEqual(complete.json(),{'session_token':app_token})
        self.assertEqual(complete.headers['cache-control'],'no-store')
