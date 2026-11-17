"""Deriv sign-in sessions are isolated from owner privileges and expire."""
import hashlib,json,time,unittest
from unittest.mock import patch
from cryptography.fernet import Fernet
from fastapi import HTTPException
from app import deriv_signin,postgres_api

class DerivSessionTests(unittest.TestCase):
    def test_invalid_token_is_rejected_before_db(self):
        with patch.object(postgres_api,'connect') as connect:
            for token in ['', 'Bearer owner-token', 'Bearer deriv_invalid']:
                with self.assertRaises(HTTPException) as e:deriv_signin.read_session(token)
                self.assertEqual(e.exception.status_code,401)
            connect.assert_not_called()

    def test_session_storage_hides_provider_and_bearer_tokens(self):
        f=Fernet(Fernet.generate_key())
        with patch.object(postgres_api,'connect') as connect,patch('app.deriv_oauth.cipher',return_value=f):
            token=deriv_signin.create_session({'access_token':'provider-secret','expires_at':time.time()+60,'client_id':'client'})
        self.assertRegex(token,r'^deriv_[A-Za-z0-9_-]{64}$')
        args=connect.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value.execute.call_args.args
        self.assertNotIn(token,str(args));self.assertNotIn('provider-secret',str(args))
        self.assertEqual(args[1][1],hashlib.sha256(token.encode()).hexdigest())

    def test_expired_or_mismatched_session_rejected(self):
        f=Fernet(Fernet.generate_key());token='deriv_'+('a'*64);digest=hashlib.sha256(token.encode()).hexdigest()
        for expiry,binding in [(time.time()-1,digest),(time.time()+60,'other')]:
            body={'encrypted_connection':f.encrypt(json.dumps({'access_token':'secret','expires_at':expiry,'client_id':'client','session_digest':binding}).encode()).decode()}
            with patch.object(postgres_api,'connect') as connect,patch('app.deriv_oauth.cipher',return_value=f),patch('app.deriv_oauth.config',return_value=('client','https://api.example/callback')):
                connect.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value.fetchone.return_value=(body,)
                with self.assertRaises(HTTPException) as e:deriv_signin.read_session('Bearer '+token)
                self.assertEqual(e.exception.status_code,401)

    def test_deriv_session_cannot_authenticate_as_owner(self):
        with patch.object(postgres_api,'connect') as connect:
            with self.assertRaises(postgres_api.postgres_identity.OwnerAuthError):
                postgres_api.postgres_identity.verify_session(connect,'Bearer deriv_'+('a'*64))
            connect.cursor.assert_not_called()

    def test_logout_deletes_only_the_matching_session(self):
        token='deriv_'+('a'*64)
        with patch.object(deriv_signin,'read_session') as read,patch.object(postgres_api,'connect') as connect:
            deriv_signin.revoke_session('Bearer '+token)
        read.assert_called_once_with('Bearer '+token)
        args=connect.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value.execute.call_args.args
        self.assertEqual(args[1],(deriv_signin.COLLECTION,hashlib.sha256(token.encode()).hexdigest()))
