# Risk Management

## Fail-closed posture

Every new order passes through `risk.checkOrderRisk()` (`src/lib/risk.ts`) **before** any fill. If any check fails, the order is set to `REJECTED` with the reasons recorded in a `TradeEvent`. No frontend toggle, environment variable, or single flag can bypass these checks.

## Independently enforced controls

| Control | Source | Enforcement |
|---|---|---|
| Emergency stop active | DB-backed `EmergencyStop` | Rejects all new entries; checked first |
| LIVE authorization | `TradingAccount.liveAuthorized` | LIVE orders rejected unless explicitly authorized |
| Max position size | `RiskLimit.maxPositionSize` | `size > max` rejects |
| Max aggregate exposure | `RiskLimit.maxAggregateExposure` | `Σ(|size×price|) + new > max` rejects |
| Max simultaneous positions | `RiskLimit.maxSimultaneousPositions` | count check |
| Max spread | `RiskLimit.maxSpreadPips` | `spread/pipSize > max` rejects |
| Max daily loss | `RiskLimit.maxDailyLossPct` | cumulative net realized vs opening capital × pct |
| Max weekly loss | `RiskLimit.maxWeeklyLossPct` | (configured; daily-window attribution is a known refinement) |
| Max drawdown | `RiskLimit.maxDrawdownPct` | cumulative net realized vs opening capital × pct |
| Max leverage | `RiskLimit.maxLeverage` | (configured; margin/leverage simulation is a known refinement) |
| Max slippage | `RiskLimit.maxSlippagePips` | (configured; fill slippage is deterministic-bounded) |
| Market hours (FX weekends) | execution engine | FX orders rejected Sat/Sun UTC |
| Market data staleness | (production) | configured max age; stale data blocks new orders |
| Connection failure | (production) | broker disconnect blocks new orders |
| Abnormal volatility | (production) | configured volatility threshold |

Limits are **never hardcoded** in the execution path. The engine loads the active versioned `RiskLimit` row; if none exists, it fails-closed to very conservative defaults (size 1, leverage 1, 2% daily loss, etc.) and flags `_defaulted: true`.

## Versioned configuration

Risk limits are **versioned**: every `PUT /api/risk/limits` retires the prior active row (`active=false`) and creates a new row with an incremented `version`. Prior versions are retained for audit. Changes are recorded in the audit log with before/after snapshots.

## Emergency stop

- **Activates:** sets `EmergencyStop.active=true`, records `activatedBy`, `activatedAt`, `reason`. Audited.
- **Effect:** `isEmergencyStopActive()` is checked at the top of `checkOrderRisk()`. All new entries are rejected with reason "Emergency stop is active."
- **Persistence:** DB-backed — survives process restarts.
- **Independence:** enforced server-side; the frontend state is irrelevant.
- **Reset:** requires explicit human action (the Deactivate button + confirm dialog).
- **Existing positions:** the emergency stop does **not** automatically liquidate open positions. Position management on emergency is a separate documented policy (below).

**Browser-verified:** activating the emergency stop, then submitting a BUY order → order REJECTED with "Emergency stop is active."

## Emergency position-management policy

When the emergency stop is active:

1. **New entries:** blocked immediately.
2. **Existing positions:** left open unless a separate liquidation decision is made. The operator may manually close positions via the Trading Terminal or Portfolio views.
3. **SL/TP:** continue to function (mark-to-market still runs).
4. **No automatic liquidation on transient errors:** a broker disconnect or reconciliation discrepancy blocks new orders but does not force-close existing exposure. Forced liquidation requires an explicit, audited operator action.

This differentiates "stop new risk" from "manage existing exposure" per directive §D5.

## Risk utilization (dashboard)

The Risk Center displays:
- Aggregate exposure vs max (progress bar, turns destructive >90%)
- Open positions vs max (progress bar)
- Net realized P&L
- Daily loss limit (opening capital × pct)
- Max drawdown limit
- Cash balance
- Active violations list

## Production hardening (refinements)

1. **Realized-by-day table:** replace cumulative net-realized daily-loss check with exact intraday attribution.
2. **Margin/leverage simulation:** model required margin per position and reject if free margin insufficient.
3. **Market data staleness:** enforce a max-age on the last candle/quote before accepting orders.
4. **Correlated exposure:** add a correlation-aware aggregate exposure cap.
5. **Abnormal volatility:** add a circuit-breaker on intraday volatility spikes.
