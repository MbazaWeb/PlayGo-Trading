"""Deriv-only sessions. These sessions never grant PlayGo owner privileges."""
import hashlib
import json
import re
import secrets
import time
from cryptography.fernet import InvalidToken
from fastapi import HTTPException

COLLECTION='deriv_signin_sessions'
TOKEN=re.compile(r'^deriv_[A-Za-z0-9_-]{64}$')


def create_session(connection):
    from app.postgres_api import connect
    from app.deriv_oauth import cipher
    token='deriv_'+secrets.token_urlsafe(48)
    digest=hashlib.sha256(token.encode()).hexdigest()
    encrypted=cipher().encrypt(json.dumps({**connection,'session_digest':digest}).encode()).decode()
    with connect() as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                cur.execute('''insert into playgo_private.documents (collection_name,document_id,body,revision)
                    values (%s,%s,%s::jsonb,0)''',(COLLECTION,digest,json.dumps({'encrypted_connection':encrypted})))
    return token


def read_session(authorization):
    from app.postgres_api import connect
    from app.deriv_oauth import cipher,config
    token=authorization.removeprefix('Bearer ') if authorization.startswith('Bearer ') else ''
    if not TOKEN.fullmatch(token):
        raise HTTPException(401,'Invalid Deriv session')
    digest=hashlib.sha256(token.encode()).hexdigest()
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute('select body from playgo_private.documents where collection_name=%s and document_id=%s',(COLLECTION,digest))
            row=cur.fetchone()
    try:
        if row is None:raise ValueError('missing session')
        body=row[0] if isinstance(row[0],dict) else json.loads(row[0])
        connection=json.loads(cipher().decrypt(body['encrypted_connection'].encode(),ttl=8*60*60))
        if connection['expires_at']<=time.time() or connection['client_id']!=config()[0] or connection['session_digest']!=digest:
            raise ValueError('expired session')
        return connection
    except (InvalidToken,ValueError,KeyError,TypeError):
        raise HTTPException(401,'Deriv session expired. Please sign in again.') from None


def revoke_session(authorization):
    from app.postgres_api import connect
    read_session(authorization)
    digest=hashlib.sha256(authorization[7:].encode()).hexdigest()
    with connect() as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                cur.execute('delete from playgo_private.documents where collection_name=%s and document_id=%s',(COLLECTION,digest))
