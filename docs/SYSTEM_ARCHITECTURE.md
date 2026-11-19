# System Architecture

## Overview

PlayGo Trading is a single-route Next.js 16 (App Router) application with a Prisma/SQLite persistence layer, a server-side trading/accounting/risk engine, and a client-side SPA dashboard. The architecture enforces a **fail-closed** posture: LIVE trading is disabled by default and cannot be enabled by a single flag.

## Stack

| Layer | Technology |
|---|---|
| Framework | Next.js 16 (App Router, Turbopack) |
| Language | TypeScript 5 (strict) |
| Styling | Tailwind CSS 4 + shadcn/ui (New York) |
| Data fetching | TanStack Query v5 |
| Database | Prisma ORM + SQLite (port of original PostgreSQL model) |
| Auth | bcryptjs + DB-backed opaque session tokens |
| Money | decimal.js (no binary floating-point for balances) |
| Charts | Custom SVG (candlestick + line) — no external chart lib |
| Icons | lucide-react |
| Theming | next-themes (dark default) |

## Module map

```
src/
  app/
    api/                      Next.js Route Handlers (server-side)
      auth/{register,login,logout,me}/
      accounts/
      market/{instruments,candles,quote}/
      orders/ + orders/[id]/
      positions/ + positions/[id]/close/
      accounting/{journals,ledger,trade-events,trial-balance,verify-integrity}/
      strategies/ + strategies/[id]/{backtest,approve}/
      risk/{limits,status}/
      emergency-stop/
      broker/connections/
      admin/{audit,health}/
      portfolio/summary/
      health/
      seed/                   dev-only idempotent seed
    page.tsx                  single client route (SPA shell)
    layout.tsx                root layout + ThemeProvider + Toaster
  components/
    app-shell.tsx             sidebar nav + header + sticky footer + view router
    theme-provider.tsx
    charts/
      candlestick-chart.tsx   SVG candlestick + line chart
    views/
      auth.tsx                login/register
      dashboard.tsx
      trading-terminal.tsx
      strategy-center.tsx
      portfolio.tsx
      risk-center.tsx
      accounting.tsx
      broker-connections.tsx
      administration.tsx
      settings.tsx
    ui/                       shadcn/ui primitives (preinstalled)
  lib/
    db.ts                     Prisma client (singleton)
    auth.ts                   password hashing, sessions, rate limiting
    api.ts                    JSON helpers, requireUser/requireAdmin
    money.ts                  Decimal-safe arithmetic + integrity hashing
    market.ts                 synthetic instrument universe + GBM candle generator
    execution.ts              PAPER order lifecycle + position management
    accounting.ts             double-entry, append-only journals, integrity
    risk.ts                   risk checks + utilization
    emergency.ts              emergency stop service
    audit.ts                  audit log + trade event recorder
    backtest.ts               deterministic strategy backtester
    seed.ts                   idempotent dev seed
  prisma/
    schema.prisma             17 models
```

## Request flow

1. Client (`app-shell.tsx`) renders a view; TanStack Query calls `/api/*` routes.
2. Route handler authenticates via `getUserFromCookie()` (DB session lookup).
3. Sensitive operations call `audit()` and `recordTradeEvent()`.
4. Financial writes go through `accounting.postJournal()` (idempotent + balanced + hashed).
5. Order creation flows through `execution.createOrder()` → `risk.checkOrderRisk()` → fill → `accounting.postTradeSettlement()`.

## Fail-closed invariants

- `TradingAccount.liveAuthorized` defaults to `false`. No code path sets it to `true` automatically.
- `risk.checkOrderRisk()` rejects any LIVE order when `liveAuthorized === false`.
- Emergency stop is DB-backed; `isEmergencyStopActive()` is checked on every new order regardless of frontend state.
- Append-only financial tables (`AccountingJournal`, `LedgerEntry`, `TradeEvent`) are only written via `create*`; the repository layer exposes no update/delete.

## Process model

This is a single Next.js process. The directive notes that long-running trading workers, persistent broker connections, and scheduled execution are **not** suitable for serverless. For production, the market-data tick loop, mark-to-market job, and broker WebSocket connection should run in a dedicated worker process (e.g. a `mini-services/` Bun service or a containerized Node worker) that shares the database. This sandbox uses on-demand MTM (called when positions are listed) and per-request quote generation as a PAPER simplification.
