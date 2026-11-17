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
  OAuth tokens identify the application on authenticated REST requests.
- `DERIV_OAUTH_ENCRYPTION_KEY`: a persistent Fernet key; server-only secret.

Register the exact redirect URI above in Deriv. Start the flow at
`https://playgo-ai-trading-api.vercel.app/deriv/connect`, authenticate as the
PlayGo owner, then authorize on Deriv. PKCE, a 10-minute state cookie, owner
session validation, and HTTPS-only HttpOnly encrypted cookies protect the flow.
The token exchange runs only on the backend. Tokens are not returned to JavaScript
or stored in plaintext. The connection expires after at most eight hours. An encrypted copy is stored in the existing private documents table, keyed by the authenticated PlayGo owner; no new database schema is required.
Deriv requires the `trade` OAuth scope for Options accounts and demo trading.
GET /api/deriv/accounts requires a PlayGo owner bearer session, returns explicitly
labelled demo and real accounts, and never substitutes demo money.
Balances are fetched from Deriv on each request and shown by currency; wallets
and MT5 balances are not included. Missing balances are unavailable, never zero.
Provider 401/403 requests reconnection; upstream failures do not expose raw data.
The account overview discovers all active Deriv Forex symbols, streams live
quotes, and displays candle history with EMA 9/21 trend lines on both demo and
real account selections. It uses Deriv's unauthenticated public market WebSocket
at `wss://api.derivws.com/trading/v1/options/ws/public`; a numeric App ID is not
required. Public market data is read-only and does not place orders.

`GET /api/deriv/accounts/{account_id}/performance` checks that the account is
present in the authenticated Deriv account list before opening its account-scoped
OTP WebSocket. It reports Deriv open-contract P&L, realized P&L from up to the
100 most recent profit-table transactions, and opposing directional positions
grouped by underlying. Account figures refresh in the frontend every 30 seconds.
The realized total may be truncated when Deriv returns 100 transactions.
Opposing positions are informational only, are not guaranteed to offset losses,
and never trigger orders. Real-account execution remains disabled.

The Deriv sign-in session also enables the explicitly started demo bot. It is
restricted server-side to verified USD demo Options accounts and uses a 5-minute
EMA 9/21 signal on EUR/USD. Upward crosses buy Rise/CALL contracts and downward
crosses buy Fall/PUT contracts. Each stake is USD 2; total demo stakes are capped
at USD 5 per UTC day, allowing at most two contracts. This caps possible stake
losses, rather than calculating realized daily P&L. The bot is driven
by requests from the open PlayGo page, trades at most one contract at a time,
and does not close an existing contract when stopped. Start/stop are available
at `/api/deriv/demo-bot/start` and `/stop`, with `/api/bot/start` and `/stop`
aliases for clients using the shorter paths. Real-account execution, deposits,
and withdrawals remain disabled.

Demo bot run history is recorded in `playgo_private.bot_runs`; the existing
`playgo_private.documents` state remains authoritative for daily stake limits
and trade recovery. Apply the updated `sql/supabase_foundation.sql` to the
PostgreSQL database before deploying this version. Each run stores only the
SHA-256 digest of its Deriv session token, never the bearer token itself.

Check `/`, `/api/health`, and `/api/ready` after deployment. A direct callback visit
without starting OAuth should return a readable HTTP 400, never a runtime crash.
Do not log OAuth authorization codes, callback query strings, or tokens. Platform
request logs may retain callback URLs; restrict their access and retention.

Tests: `python -m unittest tests.test_deriv_demo_bot tests.test_deriv_oauth tests.test_deriv_signin -v` from `backend/`.

The frontend defaults to the Deriv account view. The paper simulator is available
only through its separate view and retains its previous balance and positions.

## Sign in with Deriv and demo/real selection

PlayGo now offers Sign in with Deriv without owner credentials. The button opens
`/api/deriv/oauth/signin` in a popup. PKCE/state protect the Deriv redirect. The
frontend polls a one-time backend handoff bound to a browser-generated verifier,
so completing sign-in does not depend on the popup retaining its opener. The
callback saves only a separate PlayGo Deriv-session token server-side; the popup
closes after authorization. No credentials or tokens appear in a URL. Deriv
tokens remain encrypted server-side; the separate app bearer token is hashed for
database lookup.

These sessions can read Deriv balances, start/stop the verified demo bot, and
revoke themselves. They cannot authenticate as an owner or access the shared
paper account. Owner sign-in remains a separate option. Session lifetime is at
most eight hours.

GET /api/deriv/accounts now returns both real and demo Options accounts, preserving
Deriv's explicit account_type. The account selector displays DEMO / VIRTUAL FUNDS
or REAL / REAL FUNDS for the selected account. It never infers type from balance
or adds together accounts. Wallet and MT5 balances remain out of scope.

The existing callback URL remains unchanged. The frontend origin must appear in
CORS_ORIGINS. Public sign-in does not create a company owner or grant trading access.
