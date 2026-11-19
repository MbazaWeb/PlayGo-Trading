# Backend / Frontend Mapping

## Next.js

- Active page: `src/app/page.tsx` -> `src/components/app-shell.tsx`.
- Authentication: `/api/auth/login`, `/api/auth/me`, `/api/auth/logout` -> FastAPI PostgreSQL identity routes.
- Public registration remains rejected.
- Trading, accounting, portfolio, strategy, broker, and risk components are Next.js/React surfaces.

## FastAPI PostgreSQL API

- Entry points: `backend/app/postgres_api.py`, `backend/app/index.py`, `backend/main.py`.
- Identity: `/api/identity/*`.
- Paper state: `/api/state`, `/api/state/control`.
- Paper orders and positions: `/api/demo/orders`, `/api/paper/positions`.
- Accounting: `/api/accounting/*`.
- Signals and risk: `/api/paper/signals`, `/api/paper/automation/*`.
- Market: `/api/market/forex`, `/api/market/candles`.
- Deriv: OAuth/account/demo-bot routers mounted by `backend/app/index.py`.

## Legacy surfaces

- `src/main.tsx` and `src/pages/deriv/*` are Vite-era.
- `backend/app/main.py` is the legacy MongoDB paper-trading API.
- Most remaining Next.js routes directly use Prisma/Mongo-era helpers and require a mapping pass to proxy or replace them.
