# Architecture Conflicts

## Status

- Resolved: the root `backend/main.py` compatibility entry point now imports `backend/app/postgres_api.py` instead of the MongoDB implementation.
- Active conflict: `backend/app/main.py` remains MongoDB-backed and must be treated as legacy until explicitly retired.
- Active conflict: Next.js API routes previously mixed Prisma/Mongo-era database access with the PostgreSQL FastAPI backend.
- Resolved for authentication: Next.js login, logout, and identity-me routes now proxy the PostgreSQL owner API.
- Public registration is intentionally disabled to match the single-owner security model.
- No public Prisma schema is present; the generated `node_modules/.prisma/client/schema.prisma` is build output and not a source migration.
- The frontend contains both Next.js and Vite-era entry/component structures. The Next.js `src/app/page.tsx` entry is the active route; Vite entry points are legacy or embeddable components until build-tested.
- Supabase private tables exist in `playgo_private`; no public application tables were found during the live schema check.
