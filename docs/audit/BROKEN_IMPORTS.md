# Broken Imports and Integration Gaps

## Verified

- Backend unit tests: 384 passed and 26 skipped.
- Frontend baseline initially compiled and generated pages, but the original build script failed on Windows because `cp` was an external Unix-style command.
- Replaced the Unix copy commands with `scripts/build-next-standalone.mjs`.
- Final frontend validation: `npm run build` succeeded and generated all 41 static pages.
- Supabase readiness check passed against the configured database.

## Remaining integration review

- Several Next.js API routes still import `@/lib/db` or Prisma-era helpers. They are not the authoritative PostgreSQL path and must be migrated or proxy-wrapped before they are considered working.
- `src/components/views/auth.tsx` no longer exposes public registration and now uses the owner username contract.
- `src/services/api.ts` targets Vite-style `VITE_API_URL`; keep it as legacy/alternate frontend support until the Next entry uses a unified API contract.
- `backend/app/main.py` still imports MongoDB and requires `MONGODB_URI`; it is legacy and disconnected from the PostgreSQL deployment entry point.
- No source `prisma/schema.prisma` exists. Do not treat generated Prisma output as a recoverable schema.
