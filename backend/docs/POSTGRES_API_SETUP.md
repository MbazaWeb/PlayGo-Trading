# PostgreSQL API setup

The deployed Deriv API uses `app/index.py`, which registers OAuth, account, and demo bot routes on `app.postgres_api`. For development, use the same entry point with a disposable database.

## Configure the API

Create a repository-root `.env`:

```dotenv
PLAYGO_ENV=local
DATABASE_URL=postgresql://DB_USER:URL_ENCODED_PASSWORD@DB_HOST:5432/DB_NAME?sslmode=require
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
```

Use the connection details for your development database. If direct access is unavailable, use the Supabase Session pooler details. Keep the connection string on the server.

Apply the SQL files in this order, matching the PostgreSQL CI job:

1. [Foundation](../sql/supabase_foundation.sql)
2. [Owner identity](../sql/supabase_owner_identity.sql)
3. [Accounting integrity](../sql/supabase_accounting_integrity.sql)

From `backend/`, start `python -m uvicorn app.index:app --port 8001` in the project virtual environment. The frontend defaults to `http://127.0.0.1:8001` in local development. Check `GET /api/health` for liveness and `GET /api/ready` for database readiness.

## Identity and account data

The optional owner bootstrap is restricted to local loopback requests and requires a matching `X-PlayGo-Bootstrap-Secret` header. Configure `PLAYGO_OWNER_BOOTSTRAP_SECRET` only when provisioning an isolated development owner. The database enforces a single owner for the company.

Deriv OAuth uses a separate session. It reads balances and performance for authorized Options accounts and permits bot execution only on eligible demo accounts. OAuth settings are documented in the [Vercel and Deriv runbook](VERCEL_DERIV_OAUTH.md).

## Verification

- Run `python -m unittest discover -s tests -t . -p 'test_*.py' -v` from `backend/`.
- Database integration tests use `TEST_DATABASE_URL` for a disposable PostgreSQL database. See the [backend CI workflow](../../.github/workflows/backend-tests.yml) for setup.
- The paper operational status route, `GET /api/paper/automation/operational-status`, reports the paper risk budget. Deriv demo stake limits are maintained separately by the demo bot.
