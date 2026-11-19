# Phase D — Controlled Real-Money Pilot Report

## Status: NOT STARTED

Phase D (controlled real-money pilot) requires Phase C acceptance and explicit human authorization. Neither has occurred. No real-money orders have been placed, attempted, or simulated as real.

## D1. Live integration (engineering)

The LIVE broker adapter is **implemented but safely disabled**:
- `BrokerConnection` supports `DERIV_LIVE` mode.
- LIVE connections are created with `permissions='READ'` only.
- `risk.checkOrderRisk()` rejects any LIVE order when `TradingAccount.liveAuthorized === false`.
- No broker API tokens are stored in the codebase or database.

Production activation requires: official broker API client, secure credential management (vault), request validation, timeout/rate-limit handling, retry-safe idempotency, order reconciliation, structured audit logging.

## D2. Live execution authorization gate

See `PHASE_C_LIVE_READINESS.md` — the 10 conditions. All must be satisfied before any live order.

## D3. Real account connection

The connection workflow (built) supports: secure authentication, account identity verification, permission verification, account currency, available balance, equity, margin, open positions, transaction history, connection health, credential rotation, revocation. Before live authorization, use **read-only** account access only.

## D4. Live pilot execution (when authorized)

After explicit authorization, use only the approved: broker, account, instruments, capital allocation, risk limits, strategy version, deployment version. Start with the smallest approved capital and order size. Do not autonomously increase risk limits or capital.

## D5. Live protection

Automatically block new orders when: reconciliation fails, daily loss reached, drawdown reached, market data stale, broker inconsistent, execution state unknown, emergency stop active, monitoring unavailable, authorization revoked. Differentiate "stop new orders" from "manage existing exposure." Do not auto-liquidate on transient errors.

## D6. Live monitoring

The dashboard provides: real-time equity, open positions, realized/unrealized P&L, costs, risk exposure, broker connectivity, reconciliation status, strategy status, emergency stop status, recent orders, execution errors, audit history. Human review required during the initial 2–4 weeks.

## D7. Pilot acceptance criteria

- Clean reconciliation
- No unresolved material risk events
- Accurate financial records
- Correct emergency-stop behavior
- Stable operational performance
- No unauthorized orders
- Compliance with approved capital limits

**Do not increase capital automatically after pilot completion.**

## Phase D status

**NOT STARTED.** No `PHASE_D_LIVE_PILOT_REPORT` will be generated until Phase C is accepted and explicit human authorization is recorded. This document remains a template/stub.
