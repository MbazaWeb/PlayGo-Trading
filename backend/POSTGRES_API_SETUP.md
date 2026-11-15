# Supabase PostgreSQL API — staged local verification

This is a **separate migration API**, not the production dashboard API. The
legacy `backend/main.py` still uses MongoDB. Do not deploy or point the
production frontend at `postgres_api.py` until the remaining endpoints and
end-to-end tests are complete.

## Local environment

Create `.env` at the repository root (never commit it):

```dotenv
DATABASE_URL=postgresql://DB_USER:URL_ENCODED_PASSWORD@YOUR_SUPABASE_POOLER_HOST:5432/postgres?sslmode=require
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
PLAYGO_OWNER_BOOTSTRAP_SECRET=REPLACE_WITH_RANDOM_SECRET_AT_LEAST_32_CHARACTERS
```

Use the **actual connection details from Supabase → Connect → Session pooler**
if direct IPv6 database access is unavailable. The hostname and port above are
illustrative only; use the exact values shown in your dashboard. Do not use
the publishable/anon key as the database password. Keep DATABASE_URL strictly
server-side.

## Start the isolated API

```powershell
cd "$HOME\Documents\PlayGo-Trading"
git pull origin main
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
.\.venv\Scripts\python.exe -m uvicorn postgres_api:app --app-dir backend --port 8001
```

`GET http://127.0.0.1:8001/api/health` must return
`{"ok":true,"mode":"PAPER","database":"POSTGRESQL"}` before attempting login.

## Bootstrap safety

The one-time bootstrap endpoint is restricted to loopback connections and
requires `X-PlayGo-Bootstrap-Secret`. It inserts a single owner enforced by
a database uniqueness constraint. Never expose the bootstrap secret in the
browser or deploy it as a `VITE_*` variable.

## Not yet migrated

- Trading engine, autonomous agent cycles, order intents and recovery
- Full state persistence integration and concurrency tests
- Settlement POST routes, audit, migration/reconciliation of legacy data
- Production backend deployment, frontend `VITE_API_URL` cutover

Real-money execution remains disabled. Rotate exposed credentials before
production; do not paste them into chat or GitHub.
