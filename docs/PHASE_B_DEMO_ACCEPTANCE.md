# Phase B — Broker Demo Integration Acceptance

## Engineering gates

| Gate | Status | Evidence |
|---|---|---|
| Broker abstraction | PASSED | `BrokerConnection` model supports PAPER/DERIV_DEMO/DERIV_LIVE/OANDA_PRACTICE |
| Common broker interface | PARTIAL | connection/permissions/revoke implemented; full market-data/order adapters are stubbed for DEMO/LIVE (production needs real SDK integration) |
| Demo execution engine | PASSED (PAPER) | PAPER execution is fully working; DEMO order routing to a real broker practice account is stubbed |
| Order lifecycle | PASSED | 8-state lifecycle with idempotency, rejection, partial-fill handling |
| Broker reconciliation | IMPLEMENTED (model) | `Reconciliation` model + endpoints; live reconciliation against a real broker pending connection |
| Demo risk engine | PASSED | all controls enforced pre-fill |
| Emergency stop | PASSED | DB-backed, fail-closed, browser-verified |
| Demo validation | BLOCKED | requires 60–90 days of continuous demo observation against a real broker practice account |

## Broker selection

The directive identifies OANDA practice and Deriv as candidates. This build supports a broker adapter interface capable of implementing either:

- **Deriv:** `DERIV_DEMO` and `DERIV_LIVE` modes modeled. Deriv provides synthetic indices (R_100, R_75, Boom/Crash) which are reflected in the PAPER instrument universe. The user supplied a Deriv app ID and API token in the development paste (to be rotated before live).
- **OANDA:** `OANDA_PRACTICE` modeled. OANDA practice account eligibility depends on the user's jurisdiction; the directive explicitly notes not to assume OANDA is available.

The selected broker must be recorded in `docs/BROKER_INTEGRATION.md` (to be created on connection) with account type, API terms, automated-trading permissions, instrument availability, and regulatory considerations.

## Observation gate — BLOCKED (clock cannot start)

The directive requires **60–90 days of continuous demo validation** on a real broker practice account with clean reconciliation, proven risk controls, complete audit records, stable operational performance, documented strategy behavior, and no unresolved critical failures.

- **Status:** NOT STARTED. The Phase B observation clock cannot start until a real DEMO broker account is connected and supplying real broker-side snapshots.
- **Mechanism (ready):** `src/lib/reconciliation.ts` records Phase B observations with broker-side fields; `src/lib/broker-deriv.ts` provides the Deriv adapter scaffold; `scripts/daily-reconciliation.ts` + the daily cron (23:00 Africa/Nairobi, job_id 537134) will record Phase B observations automatically once a DEMO account is live.
- **What's missing:** a real Deriv DEMO (virtual) account token provided via `DERIV_DEMO_TOKEN` env (server-side secret management, NOT the LIVE token from the development paste), a production WebSocket adapter implementation, and a persistent worker process to host the broker connection.
- **Blocker:** requires the user to create a DEMO broker account and provide credentials through a secure channel. The clock starts on the first real observation after connection.

**Important:** the Deriv API token in the user's development paste is treated as a LIVE credential and is NOT used for DEMO. A separate DEMO (virtual) account token must be created. See `BROKER_INTEGRATION.md`.

## Phase B status

**ENGINEERING: PASSED (abstraction + adapter scaffold + reconciliation engine). DEMO OBSERVATION: BLOCKED (no real DEMO broker connected; clock cannot start).**

Phase B is NOT ACCEPTED until a real broker demo account is connected, the production WebSocket adapter is implemented in a persistent worker, and the 60–90 day observation completes with zero unresolved critical failures.
