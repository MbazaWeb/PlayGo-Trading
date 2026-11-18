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

    def test_demo_and_real_balances_remain_separately_labelled(self):
        r=self.query({'data':[{'account_id':'demo','account_type':'demo','balance':10000,'currency':'USD'},{'account_id':'real','account_type':'real','balance':0,'currency':'USD'}]})
        self.assertEqual(r.status_code,200);self.assertEqual(r.json()['accounts'],[{'account_id':'demo','account_type':'demo','balance':'10000','currency':'USD'},{'account_id':'real','account_type':'real','balance':'0','currency':'USD'}])
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

    def test_deriv_signin_session_does_not_call_owner_auth(self):
        client=AsyncMock();result=Mock(status_code=200);result.json.return_value={'data':[]};client.get.return_value=result
        with patch.object(postgres_api,'owner') as owner,patch('app.deriv_signin.read_session',return_value=self.connection),patch.object(accounts.httpx,'AsyncClient') as cls:
            cls.return_value.__aenter__.return_value=client
            response=self.client.get('/api/deriv/accounts',headers={'Authorization':'Bearer deriv_'+('a'*64)})
        self.assertEqual(response.status_code,200);owner.assert_not_called()


class AccountPerformanceTests(unittest.IsolatedAsyncioTestCase):
    async def test_account_websocket_url_is_bound_to_deriv_and_account_type(self):
        response=Mock(status_code=200)
        response.json.return_value={'data':{'url':'wss://api.derivws.com/trading/v1/options/ws/real?otp=one-time'}}
        client=AsyncMock()
        client.post.return_value=response
        account={'account_id':'real-1','account_type':'real'}
        with patch.object(accounts.httpx,'AsyncClient') as cls:
            cls.return_value.__aenter__.return_value=client
            result=await accounts._options_websocket_url({'access_token':'private-token'},account)
        self.assertEqual(result,response.json.return_value['data']['url'])
        client.post.assert_awaited_once_with(
            'https://api.derivws.com/trading/v1/options/accounts/real-1/otp',
            headers={'Authorization':'Bearer private-token'},
        )

    async def test_untrusted_websocket_url_is_rejected(self):
        response=Mock(status_code=200)
        response.json.return_value={'data':{'url':'wss://attacker.example/trading/v1/options/ws/demo?otp=one-time'}}
        client=AsyncMock()
        client.post.return_value=response
        with patch.object(accounts.httpx,'AsyncClient') as cls:
            cls.return_value.__aenter__.return_value=client
            with self.assertRaises(HTTPException) as caught:
                await accounts._options_websocket_url(
                    {'access_token':'private-token'},
                    {'account_id':'demo-1','account_type':'demo'},
                )
        self.assertEqual(caught.exception.status_code,502)

    async def test_performance_endpoint_returns_read_only_deriv_snapshot(self):
        connection={'access_token':'private-token'}
        account={'account_id':'demo-1','account_type':'demo','currency':'USD','balance':'100'}
        socket=AsyncMock()
        websocket_context=AsyncMock()
        websocket_context.__aenter__.return_value=socket
        responses=[
            {'portfolio':{'contracts':[{'contract_id':88},{'contract_id':89}]}},
            {'proposal_open_contract':{
                'contract_id':88,'symbol':'frxEURUSD','contract_type':'CALL',
                'buy_price':'4','profit':'-1','purchase_time':1700000000,'is_sold':0,
            }},
            {'proposal_open_contract':{
                'contract_id':89,'symbol':'frxEURUSD','contract_type':'PUT',
                'buy_price':'2','profit':'1','purchase_time':1700000001,'is_sold':1,
            }},
            {'profit_table':{'transactions':[
                {'contract_id':1,'symbol':'frxEURUSD','contract_type':'CALL','buy_price':'2','sell_price':'5','sell_time':1700000000},
            ]}},
        ]
        with patch('app.deriv_signin.read_session',return_value=connection), \
             patch.object(accounts,'_verified_account',new=AsyncMock(return_value=account)) as verify, \
             patch.object(accounts,'_options_websocket_url',new=AsyncMock(return_value='wss://api.derivws.com/trading/v1/options/ws/demo?otp=one-time')) as get_url, \
             patch.object(accounts.websockets,'connect',return_value=websocket_context), \
             patch.object(accounts,'_account_ws_request',new=AsyncMock(side_effect=responses)) as request:
            response=await accounts.account_performance('demo-1','Bearer deriv_'+('a'*64))
        result=json.loads(response.body)
        self.assertEqual(result['account_type'],'demo')
        self.assertEqual(result['realized_pnl'],'3')
        self.assertEqual(result['unrealized_pnl'],'-1')
        self.assertEqual(len(result['open_positions']),1)
        self.assertEqual(result['execution'],'DISABLED')
        verify.assert_awaited_once_with(connection,'demo-1')
        get_url.assert_awaited_once_with(connection,account)
        self.assertEqual(
            [call.args[1] for call in request.await_args_list],
            [
                {'portfolio':1},
                {'proposal_open_contract':1,'contract_id':88},
                {'proposal_open_contract':1,'contract_id':89},
                {'profit_table':1,'description':1,'limit':500,'offset':0,'sort':'DESC'},
            ],
        )

    async def test_unlisted_account_is_rejected_before_opening_account_stream(self):
        connection={'access_token':'private-token'}
        with patch('app.deriv_signin.read_session',return_value=connection), \
             patch.object(accounts,'_verified_account',new=AsyncMock(side_effect=HTTPException(404,'Not found'))), \
             patch.object(accounts,'_options_websocket_url',new=AsyncMock()) as get_url:
            with self.assertRaises(HTTPException) as caught:
                await accounts.account_performance('other-account','Bearer deriv_'+('a'*64))
        self.assertEqual(caught.exception.status_code,404)
        get_url.assert_not_awaited()

    async def test_account_verification_does_not_accept_another_accounts_id(self):
        response=Mock(status_code=200)
        response.json.return_value={'data':[{'account_id':'demo-1','account_type':'demo','currency':'USD','balance':'10'}]}
        client=AsyncMock()
        client.get.return_value=response
        with patch.object(accounts.httpx,'AsyncClient') as cls:
            cls.return_value.__aenter__.return_value=client
            with self.assertRaises(HTTPException) as caught:
                await accounts._verified_account({'access_token':'private-token'},'real-not-listed')
        self.assertEqual(caught.exception.status_code,404)

    def test_pnl_and_opposing_exposure_are_derived_from_deriv_positions(self):
        result=accounts._performance_response(
            {'account_id':'demo-1','account_type':'demo','currency':'USD'},
            [
                {'contract_id':1,'symbol':'frxEURUSD','contract_type':'CALL','buy_price':'5','profit':'2','purchase_time':1700000000},
                {'contract_id':2,'symbol':'frxEURUSD','contract_type':'PUT','buy_price':'3','profit':'-4','purchase_time':1700000001},
            ],
            [
                {'contract_id':3,'underlying_symbol':'frxEURUSD','contract_type':'CALL','buy_price':'5','sell_price':'0','sell_time':1700000002},
                {'contract_id':4,'underlying_symbol':'frxEURUSD','contract_type':'PUT','buy_price':'3','sell_price':'10','sell_time':1700000003},
                {'contract_id':5,'symbol':'frxEURUSD','contract_type':'PUT','buy_price':'2','sell_price':None,'sell_time':None},
            ],
        )
        self.assertEqual(result['unrealized_pnl'],'-2')
        self.assertEqual(result['realized_pnl'],'2')
        self.assertEqual(result['realized_transaction_count'],2)
        self.assertEqual([row['symbol'] for row in result['recent_closed']],['frxEURUSD','frxEURUSD'])
        self.assertEqual(result['opposing_exposure'][0]['up_stake'],'5')
        self.assertEqual(result['opposing_exposure'][0]['down_stake'],'3')
        self.assertEqual(result['opposing_exposure'][0]['opposing_stake'],'3')
