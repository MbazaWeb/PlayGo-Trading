# Phase C — Live Readiness & Capital Authorization

## Status: BLOCKED

Phase C cannot be accepted until Phase A and Phase B are accepted (both require real-world observation periods that have not started). The engineering prerequisites below are implemented; the human-authorization prerequisites are pending.

## C1. Strategy acceptance

A strategy specification must contain: entry rules, exit rules, position sizing, instruments, timeframes, market conditions, SL/TP logic, risk assumptions, expected costs, max acceptable drawdown, invalidation conditions.

**Current:** the seeded "MA Crossover (Fast/Slow)" strategy has entry/exit/positionSizing/instruments/timeframes/maxDrawdownPct recorded. It must be validated against out-of-sample and demo evidence before live consideration. Status: VALIDATED (not APPROVED).

## C2. Broker & legal readiness

Must be verified and documented by a qualified professional:

- Broker identity, account type, API terms, automated-trading permissions
- Customer eligibility (Tanzanian regulatory requirements)
- Tax and reporting considerations
- Currency and payment rules
- Broker withdrawal procedures
- Broker account security (2FA, IP allowlisting)

**Flag:** these matters require a qualified legal, tax, or regulatory professional. An automated code audit is **not** a legal opinion.

### Legal & broker eligibility engagement checklist

This checklist is a structured engagement pack for a qualified Tanzanian legal/tax professional and the chosen broker. **Every item must be answered in writing by the professional; none can be answered by code.**

#### Broker eligibility (broker + professional)
- [ ] Broker is licensed/regulated to serve customers in the user's jurisdiction (Tanzania).
- [ ] Broker offers automated/algorithmic trading on the selected account type (written confirmation attached).
- [ ] Broker API terms of service reviewed and accepted (reference + date).
- [ ] Broker permits the required order types (market, limit, stop, SL/TP) on the selected instruments.
- [ ] Broker withdrawal procedure documented and tested on DEMO.
- [ ] Broker account-security controls (2FA, IP allowlisting, API-token scoping) enabled.
- [ ] Broker rate limits and execution constraints documented and within the engine's retry-safety design.

#### Tanzanian regulatory review (qualified legal professional)
- [ ] Eligibility of the account owner to trade the selected instruments under Tanzanian law.
- [ ] Licensing/registration requirements for algorithmic trading (if any) — confirm whether the operator requires a CMSA or other license.
- [ ] Foreign-exchange controls (Bank of Tanzania) applicable to capital deposit/withdrawal and trading P&L repatriation.
- [ ] Tax treatment of trading gains/losses (income vs capital; withholding on broker remittances; VAT on services).
- [ ] AML/KYC obligations on the operator and the funding source.
- [ ] Consumer-protection and disclosure obligations (if any third-party capital is ever involved — directive: no third-party capital without separate authorization).
- [ ] Data-protection obligations (Tanzania Personal Data Protection Act 2022) for user/account data stored and processed.
- [ ] Cross-border data-transfer implications (where the broker and database are hosted).

#### Tax & reporting (qualified tax professional)
- [ ] Tax residency of the account owner confirmed.
- [ ] Record-keeping requirements for trading transactions (retain journals + trade events — the system's append-only ledger supports this).
- [ ] Annual reporting obligations and currency-conversion rules for tax filings.
- [ ] Withholding tax on broker payouts (if any) and treaty position.

#### Signed deliverables required before LIVE
1. Legal opinion letter (qualified advocate) confirming regulatory eligibility and required licenses/registrations.
2. Tax advisory memo (qualified tax advisor) confirming treatment and record-keeping.
3. Broker written confirmation of automated-trading permission.
4. Signed acceptance of broker API terms.

**An automated code audit is not a substitute for any of the above.** These items are explicitly out of scope for the engineering build and are the hard human gate for Phase C.

## C3. Capital authorization

A formal authorization document (`LIVE_AUTHORIZATION_TEMPLATE.md`) must be completed with: account owner, broker, account identifier, max initial capital, allowed instruments, max per-trade risk, daily/weekly/monthly loss limits, max drawdown, max leverage, emergency-stop authority, authorized deployment version, authorization date, approval signature.

**Never invent capital amounts or risk thresholds.**

## C4. Independent readiness assessment

The following reviews must be run and recorded:

| Review | Status |
|---|---|
| Security review | PASSED (sandbox) — see `SECURITY_MODEL.md` |
| Financial accounting review | PASSED — see `DATABASE_ARCHITECTURE.md`, `PHASE_A_ACCEPTANCE.md` |
| Strategy review | PENDING out-of-sample + demo evidence |
| Risk engine review | PASSED (sandbox) — see `RISK_MANAGEMENT.md` |
| Broker adapter review | PENDING real broker connection |
| Production infrastructure review | PENDING production deployment target |
| Disaster recovery exercise | PENDING production infra |
| Credential isolation review | PENDING (user must rotate shared credentials) |
| Incident response exercise | PENDING |

## Live execution authorization gate (10 conditions)

Live order routing requires ALL of:

1. Phase A accepted. ❌ (observation not started)
2. Phase B accepted. ❌ (observation not started)
3. Phase C accepted. ❌ (blocked on A & B)
4. Broker account verified. ❌ (no real broker connected)
5. Legal & eligibility requirements satisfied. ❌ (requires professional review)
6. Live authorization document completed. ❌ (template ready, unsigned)
7. Capital & risk limits approved. ❌
8. Approved deployment version identified. ❌
9. Emergency stop tested. ✅ (browser-verified)
10. Explicit human authorization for activation. ❌

**A single feature flag must never bypass these conditions.** The codebase enforces this: `TradingAccount.liveAuthorized` is never set automatically, and `risk.checkOrderRisk()` rejects LIVE orders when it is false.

## Phase C status

**NOT APPROVED.** Engineering prerequisites are implemented; authorization prerequisites are pending Phase A/B acceptance and human sign-off.
