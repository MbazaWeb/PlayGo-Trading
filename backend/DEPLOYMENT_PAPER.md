# PlayGo PostgreSQL API — container deployment preparation

This prepares a **paper-only** FastAPI container. It does not deploy, create a database, configure DNS, or approve production.

## Architecture
- Deploy `backend/Dockerfile.paper` using **backend/** as Docker build context.
- Entrypoint is `postgres_api:app`, **not** the legacy MongoDB `main:app`.
- PostgreSQL must be hosted separately with private/restricted networking and durable backups.
- Persistent incident spool and monitor paths require an attached durable writable volume. A platform with ephemeral filesystem cannot satisfy the production preflight merely by setting paths.
- Single worker is intentional while SQLite monitoring is host-local. Do not infer multi-host coordination.
- The API's lifespan performs database initialization and posts an idempotent synthetic opening ledger entry; starting the service is **not read-only**.

## Before deployment
1. Review code, schema migrations, and privilege model; do not use real customer data.
2. Configure host secrets: `DATABASE_URL` (PostgreSQL, `sslmode=verify-full`, hostname and trusted CA), `PLAYGO_ENV=staging`, `CORS_ORIGINS=https://YOUR-FRONTEND-ORIGIN`.
3. Configure `PLAYGO_INCIDENT_SPOOL_PATH` and `PLAYGO_SHARED_MONITOR_PATH` as **distinct absolute files** under an existing writable persistent volume. Create directories and ownership before startup.
4. Do **not** set `PLAYGO_OWNER_BOOTSTRAP_SECRET` in production. The owner-bootstrap endpoint is disabled outside local mode. Plan a controlled owner provisioning procedure separately.
5. Run `python postgres_phase7i_deployment_audit.py` with the actual staging/production environment and resolve all findings.
6. Verify migrations, least-privilege database role, TLS verification, secret rotation, backups, access logs and network policy before making API public.
7. Run `python postgres_phase7i_deployed_health.py --origin https://YOUR-API-DOMAIN` after deployment. This makes only GET requests and fails if readiness is unavailable.
8. Update frontend `VITE_API_URL` only after HTTPS API checks succeed.

## Local container build
From repository root:
```sh
docker build -f backend/Dockerfile.paper -t playgo-paper-api:local backend
```
Building the image does not need secrets or a running database. Do not run it against a production database to test startup.

## Limitations
- This image is a deployment candidate, **not** a production-readiness certificate.
- The current preflight is not enforced by the application lifespan.
- API authentication, authorization, route-level safety, and rate limiting require independent review before internet exposure.
- Existing `postgres_api.py` startup writes a synthetic ledger entry; test against an isolated disposable DB first.
- PAPER only. No real-money or broker execution.
