# PlayGo AI Trading — Forex paper trading starter

**Status: development prototype, not production ready.** All quotes are synthetic and orders are virtual. The backend persists the single paper-trading account state in MongoDB Atlas. No broker, OpenAI model, or automated strategy is connected. USDJPY is displayed but blocked from execution until proper JPY-to-USD P&L conversion is implemented. Only manually requested EURUSD/GBPUSD orders are supported. The six agent names are workflow modules/placeholders, not six running autonomous AI models.

## Local run

Create a MongoDB Atlas database user with read/write access to the app database and allow your development IP address in Atlas Network Access. Copy `.env.example` to `.env` in the project root and set `MONGODB_URI` to your Atlas connection string. Never commit `.env` or share its contents.

Backend (Python 3.11+; run commands from the project root):
```bash
cd backend
python -m venv .venv
# Windows PowerShell: .\.venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
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

The backend loads the project-root `.env` automatically. Set `MONGODB_DATABASE` to select a database (defaults to `playgo_trading`) and `CORS_ORIGINS` to a comma-separated list of allowed frontend origins. Both `http://localhost:5173` and `http://127.0.0.1:5173` are allowed by default for local development. MongoDB must be reachable at backend startup; the backend fails clearly rather than falling back to volatile in-memory state. The current prototype stores one shared paper-trading account in the `app_state` collection.

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
1. Deploy `frontend/` on Vercel and set `VITE_API_URL` to the HTTPS backend URL.
2. Deploy FastAPI on an always-on container service and set `MONGODB_URI`, `MONGODB_DATABASE`, and `CORS_ORIGINS` using the host's secret manager.
3. Configure Atlas Network Access to allow only the backend's egress IPs where possible. Use a dedicated database user with least-privilege access; never put the Atlas URI in frontend variables.
4. Before any public deployment: add authentication and user-scoped data, rate limits, durable queue/worker, idempotent order execution, reconciled balances, secrets management, logging, and metrics. The unauthenticated endpoints in this starter are for localhost only.
5. Before realistic paper trading: replace synthetic quotes with a licensed, timestamped bid/ask forex feed; implement trading sessions, holidays, pip-value conversions, margin and commissions, slippage, and reproducible backtests.
6. Keep any future live broker adapter behind a separate disabled-by-default feature flag and an explicit approval workflow.

## Important limitations
- Risk sizing includes spread conservatively but this is not a complete institutional risk engine; price gaps and slippage can exceed stops.
- For no leverage, notional is capped at account equity; with $10k this often means only a small position, below 0.5% risk.
- Daily loss reset, realized/unrealized daily P&L, pending orders, a durable audit history, fees, stale quotes, weekend markets, and authenticated multi-user accounts are **not implemented**.
- MongoDB persistence stores the latest paper-account state in one document; it is not a transactional ledger or multi-user data model.
- No financial return is guaranteed. Do not expose this starter to the public internet as-is.
