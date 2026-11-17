"""Real balance authorization, provider errors, and account separation."""
import json,time,unittest
from unittest.mock import AsyncMock,Mock,patch
from fastapi import FastAPI,HTTPException
from fastapi.testclient import TestClient
from app import deriv_accounts as accounts
from app import postgres_api

class RealBalanceTests(unittest.TestCase):
    def setUp(self):
        app=FastAPI();app.include_router(accounts.router)
        self.client=TestClient(app)
        self.connection={'owner_id':'owner-1','access_token':'private-token','expires_at':time.time()+100}

    def query(self,payload=None,status=200):
        response=Mock(status_code=status)
        response.json.return_value=payload
        if status>=400:
            response.raise_for_status.side_effect=accounts.httpx.HTTPStatusError('provider failure',request=Mock(),response=response)
        client=AsyncMock();client.get.return_value=response
        with patch.object(postgres_api,'owner',return_value='owner-1'),patch.object(accounts,'load_connection',return_value=self.connection) as load,patch.object(accounts.httpx,'AsyncClient') as cls:
            cls.return_value.__aenter__.return_value=client
            result=self.client.get('/api/deriv/accounts',headers={'Authorization':'Bearer test'})
        load.assert_called_once_with('owner-1')
        client.get.assert_awaited_once_with('https://api.derivws.com/trading/v1/options/accounts',headers={'Authorization':'Bearer private-token'})
        client.post.assert_not_called()
        self.assertNotIn('private-token',result.text)
        return result

    def test_missing_owner_auth_rejected_before_connection_read(self):
        with patch.object(postgres_api,'owner',side_effect=HTTPException(401,'Unauthorized')),patch.object(accounts,'load_connection') as load:
            self.assertEqual(self.client.get('/api/deriv/accounts').status_code,401)
            load.assert_not_called()

    def test_no_connection_is_not_fake_balance(self):
        with patch.object(postgres_api,'owner',return_value='owner-1'),patch.object(accounts,'load_connection',return_value=None),patch.object(accounts.httpx,'AsyncClient') as client:
            r=self.client.get('/api/deriv/accounts');self.assertFalse(r.json()['connected']);self.assertEqual(r.json()['accounts'],[]);client.assert_not_called()

    def test_demo_funds_excluded_and_zero_real_balance_preserved(self):
        r=self.query({'data':[{'account_id':'demo','account_type':'demo','balance':10000,'currency':'USD'},{'account_id':'real','account_type':'real','balance':0,'currency':'USD'}]})
        self.assertEqual(r.status_code,200);self.assertEqual(r.json()['accounts'],[{'account_id':'real','account_type':'real','balance':'0','currency':'USD'}])
        self.assertEqual(r.headers['cache-control'],'no-store')
        self.assertEqual(r.json()['execution'],'DISABLED')

    def test_each_currency_preserved(self):
        r=self.query({'data':[{'account_id':'usd','account_type':'real','balance':'10.25','currency':'USD'},{'account_id':'eur','account_type':'real','balance':'7.5','currency':'EUR'}]})
        self.assertEqual([a['currency'] for a in r.json()['accounts']],['USD','EUR'])
        self.assertNotIn('total',r.json())

    def test_missing_balance_is_unavailable_not_zero(self):
        r=self.query({'data':[{'account_id':'r','account_type':'real','currency':'USD'}]})
        self.assertIsNone(r.json()['accounts'][0]['balance'])

    def test_provider_401_requires_reconnect(self):
        r=self.query(status=401);self.assertEqual(r.status_code,200);self.assertEqual(r.json()['reason'],'RECONNECT_REQUIRED')

    def test_provider_403_requires_balance_scope_consent(self):
        r=self.query(status=403);self.assertFalse(r.json()['connected'])

    def test_provider_500_is_sanitized(self):
        r=self.query(status=500);self.assertEqual(r.status_code,502);self.assertNotIn('provider failure',r.text)

    def test_malformed_payload_not_accepted(self):
        self.assertEqual(self.query({'unexpected':10000}).status_code,502)

    def test_invalid_amounts_not_accepted(self):
        for value in ['NaN','Infinity',True,'not-money']:
            with self.subTest(value=value):
                self.assertEqual(self.query({'data':[{'account_id':'r','account_type':'real','currency':'USD','balance':value}]}).status_code,502)

    def test_encrypted_storage_never_writes_plaintext_token(self):
        from cryptography.fernet import Fernet
        f=Fernet(Fernet.generate_key())
        with patch.object(postgres_api,'connect') as connect,patch('app.deriv_oauth.cipher',return_value=f):
            accounts.save_connection('owner-1',self.connection)
        args=connect.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value.execute.call_args.args
        self.assertNotIn('private-token',str(args))
        body=json.loads(args[1][2]);self.assertEqual(json.loads(f.decrypt(body['encrypted_connection'].encode()))['owner_id'],'owner-1')
    def test_connection_for_another_owner_or_expired_is_rejected(self):
        from cryptography.fernet import Fernet
        f=Fernet(Fernet.generate_key())
        for owner_id,expiry in [('other-owner',time.time()+100),('owner-1',time.time()-1)]:
            connection={'owner_id':owner_id,'expires_at':expiry,'client_id':'client','access_token':'private-token'}
            body={'encrypted_connection':f.encrypt(json.dumps(connection).encode()).decode()}
            with self.subTest(owner_id=owner_id),patch.object(postgres_api,'connect') as connect,patch('app.deriv_oauth.cipher',return_value=f),patch('app.deriv_oauth.config',return_value=('client','https://api.example/callback')):
                connect.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value.fetchone.return_value=(body,)
                self.assertIsNone(accounts.load_connection('owner-1'))
