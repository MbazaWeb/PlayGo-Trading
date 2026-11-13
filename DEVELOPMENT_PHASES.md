# PlayGo AI Trading — development phases

All phases remain **paper trading only**. Do not interpret sampled synthetic quotes as market evidence or claim strategy profitability.

## Phase 1 — Core virtual account (implemented; unverified)
- Single MongoDB-backed account, synthetic quotes, virtual orders, positions, basic risk checks.
- Localhost-only write controls. No authentication, multi-tenant isolation or broker execution.

## Phase 2 — Deterministic paper agents (implemented; unverified)
- Optional read-only OANDA practice pricing, EMA(9/21) on sampled midpoints, strategy diagnostics.
- Opt-in local worker, minimum cycle interval, decision timeline, loss-streak lock, daily session reset.
- Equity samples, observed drawdown, and pair-level performance.
- **Critical**: single-document state updates and process-local cycle locks are not safe for concurrent workers.

## Phase 3 — Reporting and reproducibility (in progress)
- Completed in source: filtered/paginated closed-trade API, CSV export, UTC close timestamps for new trades.
- Next: immutable append-only trade/audit collection, event IDs, data migration, deterministic replay fixtures.
- Next: historical candle ingestion with provenance, market-hours calendar, realistic spreads and slippage.
- Next: benchmark/backtesting harness with out-of-sample testing, transaction costs, and look-ahead-bias controls.
- Gate: verify reporting API, pagination, CSV escaping, persistence and data consistency.

## Phase 4 — Secure paper platform (not started)
- Authentication, per-user account isolation, access control and protected APIs.
- Atomic MongoDB transactions or event-sourced ledger, optimistic version checks, distributed lease/idempotency.
- Background scheduler ownership and crash recovery; monitoring, metrics and alerting.
- Deployment only after automated security, integration, and concurrency checks.

## Phase 5 — Research validation (not started)
- Walk-forward validation, drawdown/stress scenarios, risk-adjusted performance and data-quality reports.
- Simulated execution model including fees, swap, slippage, partial fills, holidays and market closure.
- Explicit research approval gates; no automatic escalation to real-money trading.

## Current blockers
1. Runtime tests and GitHub CI validation are intentionally deferred by project owner; no passing result is claimed.
2. Existing README has obsolete branch and manual-only instructions; treat this roadmap and code as the current phase description.
3. API is not publicly deployable. Read endpoints currently expose the shared paper account without user auth.
4. No live broker order adapter exists or is authorized.

## Phase 6 — Regulated broker research and real-money readiness (future; NOT authorized)
- Select a broker based on licensing, jurisdiction, client-money segregation, available instruments, API terms, order types, minimum trade size, and withdrawal requirements.
- Implement a separate demo-only broker execution adapter with idempotent order IDs, execution reconciliation, spread/slippage modeling, and kill switches.
- Require an independently audited event ledger, user authentication, capital limits, loss caps, emergency stop, and full order lifecycle monitoring.
- Validate a sufficiently long forward-testing period with real broker demo data and out-of-sample research; no fixed minute/hour/day/week/month profit promise.
- Before any live execution, perform legal/regulatory review for the user's jurisdiction and obtain explicit authorization for broker, account, instrument, capital allocation and risk budget.
- Live order routing remains absent and disabled until these gates are met. No environment variable can bypass the restriction.

## Phase 3 backend update (November 2026)
- Added `backend/broker.py`: broker interface and fail-closed paper-only capabilities.
- Added `backend/periods.py`: UTC calendar minute/hour/day/week/month realized paper P&L reporting.
- Added read-only `/api/broker/capabilities` and `/api/analytics/periods`.
- Added unit tests; execution deferred.
- No deployment requested or initiated in this backend milestone.
