# Production Readiness

## Engineering readiness: COMPLETE (sandbox)

The application is engineering-complete in the Next.js sandbox:

- All required modules implemented (auth, accounts, market data, execution, accounting, risk, emergency stop, strategy/backtest, broker abstraction, audit, health, full frontend).
- Frontend and backend integrated and browser-verified.
- Database schema validated (`bun run db:push` clean).
- PAPER execution works end-to-end.
- LIVE adapter implemented and safely disabled.
- Accounting reconciles (trial balance balanced, integrity hashes match).
- Risk controls pass (emergency stop verified blocking orders).
- Security controls pass (bcrypt, sessions, RBAC, account ownership, append-only).
- Lint passes clean.
- Documentation complete.

## Production deployment (NOT YET DONE)

The directive requires a production deployment target separate from this sandbox. Required:

1. **Database migration:** SQLite → PostgreSQL 17. Apply the `REVOKE` + trigger DDL in `DATABASE_ARCHITECTURE.md` for true append-only enforcement.
2. **Worker environment:** a continuously running Node/Bun worker for: market-data tick loop, mark-to-market job, broker WebSocket connection, scheduled reconciliation. Serverless is **not** suitable for these (per directive §8).
3. **Frontend hosting:** Vercel (or equivalent) for the Next.js app and stateless API routes.
4. **Secret management:** move all credentials (DB, broker tokens, JWT secret) to a managed vault. Never in `.env` committed to git.
5. **CI/CD:** build validation, test automation, deployment rollback, backup/restore, monitoring, incident alerting.
6. **Environments:** development, disposable test, staging, production with environment-specific secrets.
7. **Security headers:** strict CSP, HSTS, X-Frame-Options DENY, nosniff, Referrer-Policy.
8. **Backups & DR:** scheduled DB backups, restore drill, disaster-recovery exercise.

## Production must NOT automatically activate live trading

The deployment pipeline must not set `liveAuthorized=true` or `LIVE_TRADING_ENABLED=true`. Live activation is a separate, documented, human-authorized action recorded in `LIVE_AUTHORIZATION_TEMPLATE.md` and the audit log.

## Credential rotation (BLOCKER — user action required)

The user shared Supabase, Deriv, GitHub PAT, and database access tokens in the development paste and stated they will rotate all credentials before going live. **These must be rotated before any production deployment or live consideration:**

- GitHub PAT (expires in 7 days per the paste)
- Supabase service-role key + JWT secret
- Deriv API token
- Database access token

Store rotated secrets in a managed vault, not in committed `.env` files.

## Live readiness: NOT APPROVED

Live readiness requires Phase A, B, C acceptance (observation periods + human authorization). None have occurred. See `PHASE_C_LIVE_READINESS.md`.

## Live execution: DISABLED

`liveTradingEnabled: false` is reported by `/api/health`. No code path enables it automatically.
