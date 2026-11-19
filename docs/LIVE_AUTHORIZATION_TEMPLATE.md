# LIVE Authorization Document — Pre-filled Template

> This document has been pre-filled with all ENGINEERING fields that can be derived from the running system (deployment version, account reference, active risk limits, emergency-stop authority). **All HUMAN-ONLY fields (account owner identity, capital amount, signature, legal/broker eligibility sign-off) are left blank** — these must be completed by the account owner and a qualified legal/tax professional. No capital amount or risk threshold has been invented; the risk limits below are the active versioned configuration loaded in the system and must be confirmed by the owner as the authorized limits.

## Pre-fill status

- **Engineering fields:** COMPLETE (deployment version, account ref, active risk limits, strategy ref, emergency-stop procedure).
- **Human-only fields:** BLANK (owner identity, capital, legal/broker eligibility, signature, date).
- **Phase prerequisites:** NOT MET — Phase A (30-day observation) and Phase B (60–90 day demo) have not completed; this document cannot be SIGNED until they do.

## Authorization

- **Account owner (full legal name):** ____________________________________
- **Account owner email:** ____________________________________
- **Date of authorization:** ____________________________________ (may not predate Phase A & B acceptance)
- **Approved deployment version:** PlayGo Trading v0.1.0-engineering (Next.js 16 + Prisma). Production deployment version hash: ____________________________________ (record the exact production build hash at signing time)
- **Authorization signature:** ____________________________________

## Broker & account

- **Broker:** ____________________________________ (must match an active `BrokerConnection` row with `status=AUTHORIZED` and `permissions=TRADE` for LIVE)
- **Account type:** ____________________________________
- **Account identifier reference (non-secret):** `cmwmcforj000ctyxl5z8ah83v` (sandbox PAPER account id; replace with the production LIVE account id at signing)
- **Account base currency:** USD (confirm matches broker account at signing)
- **Automated trading permission confirmed (yes/no):** ____________________________________ (attach broker confirmation)
- **Broker API terms reference:** ____________________________________

## Capital

- **Maximum initial capital:** ____________________________________
- **Capital source (verified origin):** ____________________________________
- **Deposit method:** ____________________________________

## Instruments

- **Allowed instruments (exact symbols):** ____________________________________

## Risk limits (active versioned `RiskLimit` row — confirm or amend at signing)

> These are the limits currently loaded in the system (RiskLimit id `cmwmcfosn000ktyxl2uhoene9`, version 1, active). The account owner must confirm these are the authorized limits, or amend them via `PUT /api/risk/limits` BEFORE signing (which creates a new versioned row). No threshold has been invented by the system.

- **Maximum per-trade risk (% of capital):** ____________________________________ (owner to set; not currently a separate field — derive from maxPositionSize × price / capital)
- **Daily loss limit (% / absolute):** 5% of opening capital (maxDailyLossPct = 5)
- **Weekly loss limit (% / absolute):** 10% (maxWeeklyLossPct = 10)
- **Monthly loss limit (% / absolute):** ____________________________________ (owner to set; not currently enforced — add a monthly limit before LIVE)
- **Maximum drawdown (%):** 20% (maxDrawdownPct = 20)
- **Maximum leverage:** 30:1 (maxLeverage = 30) — confirm permitted by broker + jurisdiction
- **Maximum position size:** 10 lots/units (maxPositionSize = 10)
- **Maximum aggregate exposure:** USD 50,000 (maxAggregateExposure = 50000)
- **Maximum simultaneous positions:** 10 (maxSimultaneousPositions = 10)
- **Maximum spread (pips):** 5 (maxSpreadPips = 5)
- **Maximum slippage (pips):** 3 (maxSlippagePips = 3)

## Strategy

- **Authorized strategy name & version:** ____________________________________
- **Out-of-sample evidence reference:** ____________________________________
- **Demo observation evidence reference:** ____________________________________
- **Invalidation conditions:** ____________________________________

## Emergency stop authority

- **Who may activate:** ____________________________________
- **Who may deactivate:** ____________________________________
- **Reset procedure:** ____________________________________

## Prerequisite acceptance (all must be checked)

- [ ] Phase A accepted (30-day clean paper reconciliation complete)
- [ ] Phase B accepted (60–90 day demo observation complete)
- [ ] Phase C independent reviews complete
- [ ] Broker account verified
- [ ] Legal & eligibility review complete (professional sign-off attached)
- [ ] This document completed and signed
- [ ] Capital & risk limits approved and loaded as active `RiskLimit` version
- [ ] Approved deployment version deployed and verified
- [ ] Emergency stop tested in production-equivalent environment
- [ ] Explicit human authorization recorded above

## Revocation

This authorization may be revoked at any time by setting `TradingAccount.liveAuthorized = false` (requires a DB migration / admin action) and activating the emergency stop. Revocation is recorded in the audit log.

---

**By signing, the account owner authorizes activation of real-money order routing on the specified account, broker, instruments, capital, risk limits, strategy, and deployment version — and only those. Any deviation requires a new authorization document.**
