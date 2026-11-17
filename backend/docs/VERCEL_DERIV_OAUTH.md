# Vercel PostgreSQL entry point and Deriv callback

The Vercel backend project uses `backend/` as its root and imports `app/index.py`.
That entry point now imports `app.postgres_api`, never the legacy MongoDB app.
The old MongoDB ledger is retained for legacy history; it is not migrated or deleted.

Production environment variables:
- `DATABASE_URL`: existing PostgreSQL connection string; server-only secret.
- `PLAYGO_ENV=production`; never deploy the owner bootstrap secret.
- `CORS_ORIGINS=https://playgo-ai-trading.vercel.app`
- `DERIV_OAUTH_REDIRECT_URI=https://playgo-ai-trading-api.vercel.app/api/deriv/oauth/callback`
- `DERIV_OAUTH_CLIENT_ID`: OAuth2 client identifier from Deriv Registered apps.
  This is distinct from the legacy numeric public-market-data App ID.
- `DERIV_OAUTH_ENCRYPTION_KEY`: a persistent Fernet key; server-only secret.

Register the exact redirect URI above in Deriv. Start the flow at
`https://playgo-ai-trading-api.vercel.app/deriv/connect`, authenticate as the
PlayGo owner, then authorize on Deriv. PKCE, a 10-minute state cookie, owner
session validation, and HTTPS-only HttpOnly encrypted cookies protect the flow.
The token exchange runs only on the backend. Tokens are not returned to JavaScript
or stored in plaintext. The browser connection expires after at most eight hours.
No payment or trading scope is requested: this initial callback only requests
`application_read`. It does not enable live execution or expose real balances/orders.

Check `/`, `/api/health`, and `/api/ready` after deployment. A direct callback visit
without starting OAuth should return a readable HTTP 400, never a runtime crash.
Do not log OAuth authorization codes, callback query strings, or tokens. Platform
request logs may retain callback URLs; restrict their access and retention.

Tests: `python -m unittest tests.test_deriv_oauth -v` from `backend/`.
