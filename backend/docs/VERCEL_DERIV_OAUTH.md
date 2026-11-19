# Vercel deployment and Deriv OAuth

Production uses two Vercel projects. The frontend project builds `frontend/` and rewrites dashboard paths to the SPA entry point via `frontend/vercel.json`. The API project builds `backend/`; Vercel's FastAPI preset selects `main.py`, which imports `app.index:app` to register the Deriv routes on the PostgreSQL API.

## Environment

| Scope | Setting | Purpose |
| --- | --- | --- |
| Frontend | `NEXT_PUBLIC_API_URL` | `https://playgo-ai-trading-api.vercel.app` |
| API | `DATABASE_URL` | Server-only PostgreSQL connection string |
| API | `PLAYGO_ENV` | `production` |
| API | `CORS_ORIGINS` | `https://playgo-ai-trading.vercel.app` |
| API | `DERIV_OAUTH_CLIENT_ID` | Deriv registered OAuth application identifier |
| API | `DERIV_OAUTH_REDIRECT_URI` | `https://playgo-ai-trading-api.vercel.app/api/deriv/oauth/callback` |
| API | `DERIV_OAUTH_ENCRYPTION_KEY` | Persistent server-only Fernet key |

Register the exact callback URI with Deriv. Configure the OAuth application for the Options account and demo execution flow. Keep API secrets in the server environment, and restrict logs that may retain callback query strings.

Dashboard sign-in is per-user Deriv OAuth. `DERIV_API_TOKEN` is not a user login credential; do not expose it in the browser or use it as a shared sign-in token.

## Sign-in and account scope

The dashboard opens `GET /api/deriv/oauth/signin` in a popup. PKCE and state protect the redirect, and the frontend completes a one-time handoff using a browser-generated verifier. Deriv credentials are encrypted server-side. The browser receives a separate PlayGo session token, which the API hashes for lookup. Deriv sign-in sessions last at most eight hours.

The owner connection flow at `/deriv/connect` is separate. Deriv sign-in grants access to the authorized Options accounts, including their explicit demo or real account type. Wallet and MT5 balances are excluded. Authenticated Options performance requests verify account membership and open an account-scoped OTP WebSocket.

## Dashboard data

| Endpoint | Source and use |
| --- | --- |
| `GET /api/market/forex` | Deriv public Forex catalog and market status |
| `GET /api/market/candles` | Deriv public candle history for the selected pair and interval |
| `GET /api/deriv/accounts` | Authenticated Options account balances and currencies |
| `GET /api/deriv/accounts/{account_id}/performance` | Portfolio, open contract details, up to 500 recent profit-table rows, and direct lookup of recent missing bot contracts |
| `GET /api/deriv/demo-bot?account_id=…` | Demo bot status, limits, and persisted trade events |
| `POST /api/deriv/demo-bot/{start,stop,cycle,resolve}` | Demo configuration and lifecycle operations |

The market page streams quotes via Deriv's public WebSocket. The P&L page refreshes every 30 seconds, supports manual refresh, and labels stale data. An unavailable closed-history request leaves verified positions and exposure visible. Opposing exposure measures stake overlap across directions on the same market. The notification bell derives profit and loss from confirmed settlements and tracks repeated alerts in browser storage.

## Demo execution

The bot uses verified USD demo Options accounts. The strategy evaluates EMA 9/21 crosses on completed five-minute candles for supported Forex pairs and Volatility Indices. Defaults are EUR/USD, a five-minute Rise/Fall contract, USD 2 per contract, and a USD 5 daily stake cap. The cap covers cumulative stake for the UTC day. The bot also checks the available demo balance and allows one contract at a time.

The open signed-in dashboard drives bot cycles. Stop prevents further entries once processed, and already submitted contracts can still settle. Trade and recovery state lives in `playgo_private.documents`, with run records in `playgo_private.bot_runs`. Each run stores the session digest. Apply the [SQL setup](POSTGRES_API_SETUP.md) before enabling demo execution.

## Deployment checks

1. Check both Vercel builds for the pushed commit. A frontend build does not verify the API build.
2. Request `/api/health` and `/api/ready` on the API origin, then open the frontend dashboard routes directly.
3. Sign in and verify the selected account ID, balance, portfolio, and closed results against Deriv. A direct callback visit without an OAuth flow should return HTTP 400.
4. Use an authorized demo account for trade verification. Confirm the purchase and settlement IDs, P&L, and notification. Keep credentials and authorization codes out of logs.
