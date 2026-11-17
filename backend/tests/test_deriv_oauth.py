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
        subprocess.run([sys.executable,'-c',code],check=True)

    def test_connection_page(self):
        r=self.client.get('/deriv/connect');self.assertEqual(r.status_code,200)
        self.assertEqual(r.headers['cache-control'],'no-store')

    def test_start_is_pkce_and_cookie_encrypted(self):
        r=self.begin();self.assertEqual(r.status_code,303)
        params=parse_qs(urlsplit(r.headers['location']).query)
        self.assertEqual(params['code_challenge_method'],['S256'])
        self.assertEqual(params['scope'],['application_read'])
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
        with patch.object(postgres_api,'owner',return_value='owner-id'),patch.object(oauth.httpx,'AsyncClient') as cls:
            cls.return_value.__aenter__.return_value=client
            r=self.client.get('/api/deriv/oauth/callback',params={'code':'test-code','state':state})
        self.assertEqual(r.status_code,200);self.assertIn('Deriv connected',r.text)
        self.assertNotIn('test-private-token',r.text+r.headers['set-cookie'])
        self.assertNotIn('test-code',r.text)
        token_cookie=self.client.cookies.get(oauth.CONNECTION_COOKIE)
        data=json.loads(oauth.cipher().decrypt(token_cookie.encode()))
        self.assertEqual(data['owner_id'],'owner-id')
        self.assertIsNone(self.client.cookies.get(oauth.FLOW_COOKIE))

    def test_expired_flow_rejected(self):
        self.begin()
        with patch.object(Fernet,'decrypt',side_effect=oauth.InvalidToken):
            self.assertEqual(self.client.get('/api/deriv/oauth/callback?code=x&state=x').status_code,400)
