# PlayGo Trading

PlayGo is a Deriv Options dashboard with public Forex market data, authenticated account reporting, and a demo-only trading bot. The PostgreSQL paper-trading engine is a separate execution environment.

## Dashboard

- [Account](https://playgo-ai-trading.vercel.app/account) shows balances for Deriv Options accounts. Deriv identifies each account as demo or real. Demo balances use virtual funds.
- [Market](https://playgo-ai-trading.vercel.app/market) is public. It streams Forex quotes and offers pair search, Open/Closed/Suspended filters, and candlestick intervals from 1 minute to 1 day.
- [Trade Bot](https://playgo-ai-trading.vercel.app/trade-bot) supports verified USD demo Options accounts. Choose a Forex pair or supported Volatility Index, direction, duration, stake, and daily stake cap. The bot checks for EMA 9/21 crosses using completed five-minute candles. It shows timestamped trade events, confirmed contract results, P&L, and win rate.
- [Profit, loss & hedge exposure](https://playgo-ai-trading.vercel.app/pnl-hedge) uses the selected Deriv account's portfolio and closed history. It shows contract-level results, directional stake overlap, and a CSV export. Account data refreshes every 30 seconds and can be refreshed manually.
- The notification bell checks for confirmed profits and losses, Forex status changes, and bot activity while the dashboard is open. Recent alerts are stored in the browser.
- **Agents** (`/agents`) shows observed demo bot results, recent activity, and the evidence required to advance through the operating phases.

The demo bot checks for trades while its signed-in dashboard is open. Stop prevents new entries once processed by the server. Contracts already submitted can complete at Deriv. Real accounts are read-only. Digits contracts and unattended cloud execution are outside the current build.

## Local development

Use Python 3.11+, Node.js 20+, and an isolated PostgreSQL database. Configure the repository-root environment using the [PostgreSQL setup guide](backend/docs/POSTGRES_API_SETUP.md).

From the repository root, start the API:

```powershell
Set-Location backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.index:app --reload --port 8000
```

In a second terminal at the repository root, start the frontend:

```powershell
Set-Location frontend
$env:VITE_API_URL = 'http://127.0.0.1:8000'
npm.cmd ci
npm.cmd run dev
```

Open [the local dashboard](http://localhost:5173). OAuth testing requires a registered HTTPS callback and a matching allowed frontend origin.

## Verification and deployment

- From `backend/`, run `python -m unittest discover -s tests -t . -p 'test_*.py' -v` with the project environment activated.
- From `frontend/`, run `npm run build`.
- Production uses separate Vercel projects for the frontend and API. Pushes to `main` trigger builds for the connected projects. Check both deployment states and the affected dashboard flow.
- See the [Vercel and Deriv runbook](backend/docs/VERCEL_DERIV_OAUTH.md), [paper container guide](backend/docs/DEPLOYMENT_PAPER.md), and [development history](DEVELOPMENT_PHASES.md).
