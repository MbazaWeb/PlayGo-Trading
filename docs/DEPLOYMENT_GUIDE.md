# Deployment Guide

## Sandbox (current)

- `bun run dev` starts Next.js on port 3000 (Turbopack).
- SQLite database at `file:./db/custom.db`.
- `bun run db:push` syncs the Prisma schema.
- `POST /api/seed` (dev-only, idempotent) provisions the demo user, PAPER account, opening capital, instruments, strategies, risk limits, and health baseline.

## Production target architecture

```
[ Vercel / CDN ]  ── Next.js app (frontend + stateless API routes)
        │
        ├─ [ Worker container (Bun/Node) ]
        │     ├─ market-data tick loop
        │     ├─ mark-to-market job
        │     ├─ broker WebSocket connection
        │     └─ scheduled reconciliation
        │
        ├─ [ PostgreSQL 17 ]
        │     ├─ playgo_app role (INSERT+SELECT on financial tables)
        │     └─ playgo_audit role
        │
        └─ [ Secret vault ] (DB creds, broker tokens, JWT secret)
```

## Environments

| Env | Purpose | Secrets |
|---|---|---|
| development | local dev | local SQLite, no real creds |
| disposable test | throwaway integration tests | isolated DB, mock broker |
| staging | pre-production mirror | staging broker demo creds |
| production | live | vault-managed, rotated |

## Database migration (SQLite → PostgreSQL)

1. Provision PostgreSQL 17.
2. Point `DATABASE_URL` at the pooler.
3. `prisma migrate deploy` (generate migrations from `schema.prisma`).
4. Apply the `REVOKE` + trigger DDL from `DATABASE_ARCHITECTURE.md`.
5. Run the opening-capital seed for each production account.

## CI/CD

- Build validation on every PR (`bun run lint`, type-check, tests).
- Test automation: unit, integration, security, accounting, transaction rollback, concurrency, API, frontend.
- Deployment rollback: keep the previous deployment tagged; rollback is a one-command redeploy.
- Backup & restore: scheduled `pg_dump`, restore drill quarterly.

## Monitoring

- `/api/health` for liveness/readiness.
- `SystemHealth` table for component-level status.
- Audit log for all sensitive actions.
- Production alerting on: emergency stop activation, reconciliation discrepancy, daily-loss breach, broker disconnect, DB outage.

## Production must NOT auto-activate live trading

The deployment pipeline must not inject `liveAuthorized=true` or any `LIVE_TRADING_ENABLED` flag. Live activation is a separate, documented, human-authorized action (see `LIVE_AUTHORIZATION_TEMPLATE.md`).
