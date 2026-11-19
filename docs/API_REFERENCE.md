# API Reference

All endpoints are relative to the app root. All mutating requests require a valid `playgo_session` cookie (DB-backed session). `401` responses indicate no/expired session. `403` indicates insufficient role.

## Authentication

| Method | Path | Body | Returns |
|---|---|---|---|
| POST | `/api/auth/register` | `{ email, password, name? }` | `{ user, account }` + sets cookie |
| POST | `/api/auth/login` | `{ email, password }` | `{ user }` + sets cookie |
| POST | `/api/auth/logout` | — | `{ ok: true }` + clears cookie |
| GET | `/api/auth/me` | — | `{ user, account }` or `{ user: null }` |

Rate-limited: 20 requests / 60s / IP on register & login.

## Accounts

| Method | Path | Notes |
|---|---|---|
| GET | `/api/accounts` | List caller's trading accounts |
| POST | `/api/accounts` | Create PAPER/DEMO/LIVE account (LIVE never auto-authorized) |

## Market data

| Method | Path | Query | Returns |
|---|---|---|---|
| GET | `/api/market/instruments` | — | `{ instruments[] }` |
| GET | `/api/market/candles` | `symbol, timeframe, bars=120` | `{ candles[], source:'synthetic', isPaper:true }` |
| GET | `/api/market/quote` | `symbol` | `{ quote: { bid, ask, mid, spread, pip, precision, ts, source, isPaper } }` |

All market data is **synthetic** and clearly labeled `isPaper: true`.

## Orders & positions

| Method | Path | Body/Query | Returns |
|---|---|---|---|
| GET | `/api/orders` | `accountId` | `{ orders[] }` (last 100, MTM refreshed) |
| POST | `/api/orders` | `{ accountId, symbol, side, type, size, price?, stopLoss?, takeProfit?, clientOrderId? }` | `{ order, risk, idempotent? }` |
| GET | `/api/orders/[id]` | — | `{ order, events[] }` |
| GET | `/api/positions` | `accountId` | `{ positions[] }` |
| POST | `/api/positions/[id]/close` | — | `{ positionId, reason, realizedPnl }` |

Order lifecycle: `CREATED → VALIDATED → RISK_APPROVED → SUBMITTED → ACCEPTED → FILLED | PARTIALLY_FILLED | CANCELLED | REJECTED`.

## Accounting

| Method | Path | Query | Returns |
|---|---|---|---|
| GET | `/api/accounting/journals` | `accountId` | `{ journals[] }` (with entries) |
| GET | `/api/accounting/ledger` | `accountId` | `{ entries[] }` |
| GET | `/api/accounting/trade-events` | `accountId` or `orderId` | `{ events[] }` |
| GET | `/api/accounting/trial-balance` | `accountId` | `{ trialBalance, cash, realizedPnl, fees, unrealizedPnl, equity, openPositions }` |
| GET | `/api/accounting/verify-integrity` | `accountId` | `{ checked, valid, invalid, mismatches[] }` |

## Strategies & backtests

| Method | Path | Body | Returns |
|---|---|---|---|
| GET | `/api/strategies` | — | `{ strategies[] }` (with recent backtests) |
| POST | `/api/strategies` | `{ name, description?, entryRules?, exitRules?, positionSizing?, instruments?, timeframes?, maxDrawdownPct? }` | `{ strategy }` |
| POST | `/api/strategies/[id]/backtest` | `{ instrument?, timeframe?, days?, params? }` | `{ result }` (12 metrics + equity curve + warnings) |
| POST | `/api/strategies/[id]/approve` | — | `{ strategy }` (status → APPROVED) |

Backtest result shape: `{ netReturn, netReturnPct, maxDrawdown, maxDrawdownPct, sharpe, sortino, calmar, winRate, profitFactor, expectancy, avgGain, avgLoss, exposure, turnover, trades, transactionCosts, equityCurve[], warnings[] }`.

## Risk & emergency stop

| Method | Path | Body/Query | Returns |
|---|---|---|---|
| GET | `/api/risk/status` | `accountId` | `{ account, utilization, emergencyStop, violations[] }` |
| GET | `/api/risk/limits` | `accountId` | `{ limit }` (current active version) |
| PUT | `/api/risk/limits` | `{ accountId, ...fields }` | `{ limit }` (new versioned row) |
| GET | `/api/emergency-stop` | `accountId` | `{ emergencyStop: { active, reason, activatedAt, deactivatedAt } }` |
| POST | `/api/emergency-stop` | `{ accountId, action:'activate'|'deactivate', reason? }` | `{ emergencyStop }` |

## Broker connections

| Method | Path | Body | Returns |
|---|---|---|---|
| GET | `/api/broker/connections` | `accountId` | `{ connections[] }` |
| POST | `/api/broker/connections` | `{ accountId, broker, mode?, accountRef? }` | `{ connection }` (LIVE → READ perms only) |
| DELETE | `/api/broker/connections` | `?id=` | `{ connection }` (status → REVOKED) |

## Admin

| Method | Path | Query | Role | Returns |
|---|---|---|---|---|
| GET | `/api/admin/audit` | `action?, limit?` | ADMIN | `{ logs[] }` |
| GET | `/api/admin/health` | — | ADMIN | `{ users[], accounts[], health[] }` |

## System

| Method | Path | Returns |
|---|---|---|
| GET | `/api/health` | `{ status, components, version, liveTradingEnabled:false }` |
| POST | `/api/seed` | dev-only idempotent seed (disabled in production) |

## Error shape

All errors return `{ error: string, details?: unknown }` with an appropriate HTTP status (400, 401, 403, 404, 429, 500).
