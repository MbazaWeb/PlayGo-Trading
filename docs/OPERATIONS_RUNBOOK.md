# Operations Runbook

## Daily operations

1. **Reconciliation:** run `verifyIntegrity()` + trial-balance check for each PAPER/DEMO account. Record a `Reconciliation` row (`status=CLEAN` or `DISCREPANCY`). On DISCREPANCY, block new risk-taking orders until resolved.
2. **Backup:** verify the scheduled `pg_dump` succeeded; verify a restore drill quarterly.
3. **Health check:** monitor `/api/health` and the `SystemHealth` table. Page on any component `DOWN`.
4. **Audit review:** review the day's audit log for `EMERGENCY_STOP_ACTIVATE`, `RISK_LIMIT_UPDATE`, `BROKER_REVOKE`, failed logins.
5. **Risk review:** confirm no risk limits were breached; confirm daily-loss utilization.

## Weekly operations

- Broker reconciliation (DEMO/LIVE): compare internal vs broker orders/positions/balances.
- Credential rotation check: verify no credential is past its rotation window.
- Incident review: review any incidents from the week.

## Monthly operations

- Full broker reconciliation at end of month.
- Risk-limit review: confirm active limits match the authorized configuration.
- Strategy review: confirm approved strategies still match out-of-sample expectations.

## Quarterly operations

- Strategy review (per directive §E).
- Disaster-recovery exercise.
- Dependency security scan + update.
- Credential rotation drill.

## Emergency stop procedure

1. **Activate:** Risk Center → Activate (confirm dialog). Or directly via `POST /api/emergency-stop` with `{ accountId, action: 'activate', reason }`.
2. **Effect:** all new entries blocked immediately; persists across restarts.
3. **Existing positions:** left open unless a separate liquidation decision is made.
4. **Reset:** Risk Center → Deactivate (confirm dialog). Requires explicit human action.

## Restart recovery

- Sessions are DB-backed; users stay logged in across restarts.
- Orders in flight: `clientOrderId` idempotency means a retried submission after restart returns the original order (no duplication).
- Opening capital journal: `ref='opening-capital:<accountId>'` is unique; startup re-run never duplicates.
- Mark-to-market runs on demand when positions are listed; a production worker should run it on a fixed cadence.

## Worker supervision (production)

- The worker process must be supervised (systemd, Docker restart policy, or k8s liveness probe).
- Distributed worker ownership: only one worker owns a trading task at a time (use a DB-backed lease or leader election).
- On crash: the supervisor restarts the worker; in-flight broker requests are reconciled before resubmission (never blindly retry).

## Logging

- Prisma logs `warn` + `error` only (no query logging in production).
- Audit log captures all sensitive actions with before/after snapshots.
- Never log: access tokens, refresh tokens, client secrets, passwords, DB credentials, full authorization headers.
