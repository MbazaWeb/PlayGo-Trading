# Duplicate Modules

- `backend/app/main.py` and `backend/app/postgres_api.py` are separate FastAPI implementations. The MongoDB implementation is legacy; the PostgreSQL implementation is the target.
- `backend/main.py` and `backend/postgres_api.py` are compatibility wrappers. `backend/main.py` now targets PostgreSQL; `backend/postgres_api.py` already targets it.
- `backend/app/ledger.py` and `backend/app/postgres_ledger.py` duplicate paper-ledger responsibilities for MongoDB and PostgreSQL.
- `backend/app/accounting.py` and `backend/app/postgres_accounting.py` implement accounting for the two persistence systems.
- `backend/app/identity.py` and `backend/app/postgres_identity.py` implement separate auth models.
- `backend/app/demo_orders.py` and `backend/app/postgres_demo_orders.py` provide MongoDB/PostgreSQL demo-order implementations.
- `backend/app/positions.py` is not present; PostgreSQL position logic is split across `postgres_positions.py` and `postgres_position_lifecycle.py`.
- Frontend API helpers have legacy Prisma-era and FastAPI-era paths. `src/lib/backend.ts` is the server-side bridge for the PostgreSQL API; `src/lib/db.ts` and Prisma helpers should not be used for authoritative state.
