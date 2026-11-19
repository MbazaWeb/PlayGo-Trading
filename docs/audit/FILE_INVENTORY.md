# File Inventory

Generated from the project inventory and live workspace inspection.

## Physical layout

- Frontend application files are under `frontend/`, including `src/`, `public/`, package manifests, Next.js configuration, scripts, and frontend tests.
- FastAPI application files are under `backend/app/`; backend tests, SQL, scripts, docs, requirements, Docker files, virtual environment, and mini-services are under `backend/`.
- Supabase files are under `supabase/`.

- Inventoried application files: 362 at source snapshot time.
- Next.js application: `src/app`, `src/components`, `src/lib`, `src/services`, `src/hooks`, `src/types`.
- FastAPI application: `backend/app` (52 Python modules), `backend/tests` (72 test modules).
- SQL: three existing PlayGo Supabase SQL files under `backend/sql`.
- Supabase migration history: three generated migration files under `supabase/migrations`.
- Legacy and compatibility entry points:
  - `backend/app/main.py` (MongoDB implementation)
  - `backend/main.py` (now targets the PostgreSQL API)
  - `backend/app/postgres_api.py` (PostgreSQL paper-trading API)
  - `backend/app/index.py` (Vercel/PostgreSQL entry point)
- Mini-services: `mini-services/deriv-adapter`, `mini-services/playgo-worker`.
- Vite-era components and pages remain under `src/main.tsx`, `src/AccountWorkspace.tsx`, `src/DerivMarketPanel.tsx`, and `src/pages/deriv`.
- Dependency directories, virtual environments, build caches, and generated `.next` output are not application source.

No `.env` values or credentials are recorded in this audit.
