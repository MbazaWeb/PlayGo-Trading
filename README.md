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

## Phase 2 — market-data-assisted paper agents (feature branch)

The Phase 2 implementation adds `backend/agents.py`, `backend/feed.py`,
`backend/worker.py`, `backend/test_agents.py`, `backend/test_feed.py`,
a strategy proposal history on the dashboard, and automated simulation endpoints.

**Important boundaries**: all executions remain PAPER, and there is deliberately
NO broker order endpoint. Six agent *functions/stages* are not six independent
LLMs. The strategy is a deterministic EMA(9/21) crossover on sampled mid-quotes
(currently *not OHLC candles*). It is a software demonstration, **not a
validated profit-making strategy or a reliable backtest**.

### Running Phase 2 on Windows

From the exact checkout folder `C:\Users\Mbaza\Documents\PlayGo Trading`:

```powershell
git fetch origin
git switch feature/phase-2-paper-agents
git pull --ff-only origin feature/phase-2-paper-agents
Copy-Item .env.example .env  # only if .env does not already exist
# Edit .env, configure MongoDB URI, and leave FOREX_FEED=synthetic initially.
cd backend
py -m pip install -r requirements.txt
py -m unittest discover -s . -p "test_*.py" -v
py -m uvicorn main:app --reload --port 8000
```

In a second terminal:
```powershell
cd "C:\Users\Mbaza\Documents\PlayGo Trading\frontend"
npm ci
npm run dev
```

In a third terminal, if automatic 60-second simulation cycles are desired:
```powershell
cd "C:\Users\Mbaza\Documents\PlayGo Trading\backend"
py worker.py
```

**Run only one backend process and one worker against a given shared paper account.**
The current MongoDB single-document state is not concurrency-safe or multi-tenant.
There is no distributed lock, compare-and-swap state version, or user isolation.
For testing, you can press **Run agent cycle** on the dashboard to execute one
synthetic quote step plus strategy/risk/virtual execution.

### Read-only OANDA practice pricing (optional)

OANDA practice credentials are optional. If your practice account is eligible
for the v20 API, set these fields **in backend .env only**:

```dotenv
FOREX_FEED=oanda_practice
OANDA_ACCOUNT_ID=YOUR_PRACTICE_ACCOUNT_ID
OANDA_API_TOKEN=YOUR_PRACTICE_TOKEN
```

The backend requests `EUR_USD` and `GBP_USD` bid/ask quotes from the
OANDA **practice** pricing endpoint. It rejects missing, crossed, non-tradeable,
or >120-second stale quotes and pauses new entries on a feed error.
Never place tokens in `VITE_*` variables or commit them to Git.

### API changes

- `POST /api/auto-cycle`: advance quotes (synthetic or read-only OANDA
  practice), evaluate deterministic strategy, route proposals through existing
  risk checks, and only then create virtual orders
- `GET /api/agents/config`: describe feed, worker configuration and paper mode
- `GET /api/status`: also returns `automation` and `signals` fields

### Safety / deployment gates

- Phase 2 write API is restricted to requests from loopback when
  `PLAYGO_ENV=local`, and blocked entirely otherwise. It lacks authentication;
  **do not expose FastAPI to the internet or a reverse proxy**.
- Dashboard may be deployed as a read-only demonstration; do not include
  `MONGODB_URI`, `OANDA_API_TOKEN`, or `OANDA_ACCOUNT_ID` in frontend build vars.
- Production release requires authentication, user-scoped accounts, safe session
  management, transactional ledgers, idempotent queued execution, durable
  distributed locking, validated historical candle data, weekend/calendar
  protections, fees and slippage, proper pip-value conversion, risk and
  integration testing, and observability.
- USDJPY remains **display-only**; quote currency conversion is not yet
  implemented. No leveraged trading; size is capped by available virtual equity.
- This implementation is for development/paper simulation. Returns cannot be
  inferred from synthetic runs or from social-media trading videos.
