# Supabase Migration Plan

## Discovered state

The live Supabase project was reachable and contains:

- `playgo_private.documents`
- `playgo_private.owner_sessions`
- `playgo_private.trade_events`
- `playgo_private.accounting_journals`
- `playgo_private.bot_runs`
- `playgo_private.owners`

No public application tables were detected.

## Migration history

The existing SQL under `backend/sql` was converted into hand-authored imperative migrations under `supabase/migrations`:

1. Private persistence foundation.
2. Owner identity and owner-session foreign key.
3. Append-only accounting and trade-event integrity.

## Security decisions

- Keep trading, identity, accounting, and audit data in `playgo_private`.
- Do not grant `anon` or `authenticated` Data API access.
- Enable RLS on private tables.
- Use a server-side `DATABASE_URL` connection only.
- Do not expose service-role or secret keys to browser code.
- Migrations must be reviewed with Supabase advisors and a remote diff before production application.

## Execution status

- Live readiness: passed.
- Migration files: created and populated.
- Frontend build: passed.
- Backend unit suite: 384 passed, 26 skipped, 24 subtests passed.
- Local migration discovery: not run successfully because the local Supabase Docker instance was not running.
- Remote migration application: not claimed; the live schema may predate migration history.
- Production cutover: requires schema diff, advisor review, and an isolated database test run.
