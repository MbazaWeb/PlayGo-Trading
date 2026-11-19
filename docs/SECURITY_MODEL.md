# Security Model

## Authentication

- **Password storage:** bcrypt with cost factor 12 (`src/lib/auth.ts`). No plaintext passwords stored.
- **Sessions:** opaque 32-byte random tokens (`crypto.randomBytes`), stored in the `Session` table with a 7-day expiry. No JWTs — rotation/revocation is a DB delete.
- **Cookie:** `playgo_session`, `HttpOnly`, `SameSite=Lax`, `Secure` in production, `Path=/`.
- **Session validation:** every request re-queries the DB; expired sessions are deleted on read.
- **Logout:** deletes the session row and clears the cookie.

## Authorization

- **Role-based:** `User.role` is `USER` or `ADMIN`. Admin routes (`/api/admin/*`) require `requireAdmin()`.
- **Account ownership:** every trading-account-scoped query filters by `userId`. One user cannot read or mutate another user's account (`getTradingAccount()` throws if `userId` mismatches).
- **LIVE authorization:** `TradingAccount.liveAuthorized` defaults to `false`. No code path sets it to `true` automatically. The risk engine rejects any LIVE order when this is false.

## Rate limiting

- In-memory per-process bucket: 20 requests / 60s / IP on `/api/auth/register` and `/api/auth/login`.
- Production should move to a durable store (Redis) for multi-instance correctness.

## Input validation

- All API bodies are parsed defensively (`parseBody` swallows malformed JSON).
- Order size validated against `Instrument.minSize` / `maxSize`.
- Email format validated on register.
- Password minimum 10 characters.
- Decimal inputs parsed via `decimal.js` (rejects NaN/Infinity).

## Secret management

- **No secrets in frontend code.** The `z-ai-web-dev-sdk` (if used) must remain server-side.
- **No credentials committed.** The `.env` contains only `DATABASE_URL` (local SQLite path). Supabase/Deriv credentials from the user's paste are **not** stored in the repo or `.env`.
- **Broker credentials:** the `BrokerConnection` model stores only an `accountRef` (non-secret identifier). Real API tokens must live in server-side secret management (env vars / vault), never in the database in plaintext, never in frontend code.
- **Logs:** the codebase never logs access tokens, refresh tokens, client secrets, passwords, DB credentials, or full authorization headers. Prisma logging is restricted to `warn` + `error` (no query logging in production).

## CORS / headers

- The Next.js dev server binds to localhost + the sandbox network interface.
- A Caddy gateway fronts the app. Cross-origin requests are confined to the gateway.
- Production should add a strict CSP, `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`, and HSTS.

## SQL injection

- All data access is via Prisma parameterized queries. No raw SQL string concatenation.

## CSRF

- State-changing endpoints require a valid session cookie and use `SameSite=Lax`. For production with cross-site traffic, add a CSRF token (double-submit or synchronizer-token pattern).

## Append-only integrity

- Financial tables (`AccountingJournal`, `LedgerEntry`, `TradeEvent`) are written once and never updated/deleted at the repository layer.
- Each journal stores a SHA-256 integrity hash; `verifyIntegrity()` recomputes on read. Any mismatch is surfaced in the Accounting view's Integrity tab.
- See `DATABASE_ARCHITECTURE.md` for the PostgreSQL `REVOKE` + trigger DDL.

## Credential rotation (per user's stated intent)

The user shared Supabase, Deriv, and a GitHub PAT in the development paste and stated they will rotate all credentials before going live. **Action required before any LIVE consideration:**

1. Rotate the GitHub PAT (the paste noted it expires in 7 days).
2. Rotate the Supabase service-role key and JWT secret.
3. Rotate the Deriv API token.
4. Rotate the database access token.
5. Store all production secrets in a managed secret store, not `.env` files committed to git.

This is tracked as a hard blocker in `FINAL_PROJECT_REPORT.md`.
