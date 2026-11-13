# PlayGo AI Trading — Forex paper trading starter

**Status: development prototype, not production ready.** All quotes are synthetic, orders are virtual, and the backend holds state in memory. No broker, OpenAI model, Supabase persistence, or automated strategy is connected yet. USDJPY is displayed but deliberately blocked from execution until proper JPY-to-USD P&L conversion is implemented. Only manually requested EURUSD/GBPUSD orders are supported. The six agent names are workflow modules/placeholders, not six running autonomous AI models.

## Local run

Backend (Python 3.11+):
```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```
Frontend (Node 20+):
```bash
cd frontend
npm install
npm run dev
```
Open http://localhost:5173. Press **Start paper engine**, **Simulate tick**, then optionally place an EURUSD or GBPUSD order. The engine is manually ticked; it does not scan autonomously yet.

## API
- GET `/api/status` portfolio, quotes, positions, agent logs
- POST `/api/start` enable virtual entries
- POST `/api/stop` disable new entries
- POST `/api/tick` generate synthetic prices and check SL/TP
- POST `/api/orders` JSON `{ "pair":"EURUSD", "side":"BUY", "stop_pips":20, "take_profit_pips":40 }`
- POST `/api/positions/{id}/close` manual virtual close
- GET `/api/health`

## Six-agent target architecture
1. Scanner: validate freshness, spread, and session of broker-provided bid/ask quotes.
2. Strategy: reproducible candle-based signals; AI explanations only.
3. Risk Checker: position sizing, portfolio risk, daily drawdown, exposure and kill switch.
4. Executor: paper fill simulator with spreads, fees, latency, slippage and order lifecycle.
5. Logger: append-only order and decision audit records.
6. Supervisor: coordinate jobs, enforce idempotency, restart recovery, stale-data shutdown.

## Deployment plan
1. Create private GitHub repo; push frontend and backend directories.
2. Deploy `frontend/` on Vercel. Set `VITE_API_URL` to the HTTPS backend URL.
3. Deploy FastAPI on an always-on container service (e.g. Render/Railway/Fly) and set `CORS_ORIGINS` to the Vercel origin.
4. Apply `supabase/schema.sql` in a dedicated Supabase project. Schema is **not yet wired** into the starter backend.
5. Before any public deployment: add Supabase JWT verification, user-scoped DB access, backend-only service key, rate limits, durable queue/worker, persistent position state, idempotent order execution, reconciled balances, secrets management, logging and metrics. The unauthenticated endpoints in this starter are for localhost only.
6. Before realistic paper trading: replace synthetic quotes with a licensed, timestamped bid/ask forex feed; implement trading sessions, holidays, pip-value conversions, margin and commissions, slippage, and reproducible backtests.
7. Keep any future live broker adapter behind a separate disabled-by-default feature flag and an explicit approval workflow.

## Important limitations
- Risk sizing includes spread conservatively but this is not a complete institutional risk engine; price gaps and slippage can exceed stops.
- For no leverage, notional is capped at account equity; with $10k this often means only a small position, below 0.5% risk.
- Daily loss reset, realized/unrealized daily P&L, pending orders, persistent audit, fees, stale quotes, weekend markets, and authenticated multi-user accounts are **not implemented**.
- The database schema is an initial foundation and needs migrations, grants, tests, and a transactional ledger before production use.
- No financial return is guaranteed. Do not expose this starter to the public internet as-is.
