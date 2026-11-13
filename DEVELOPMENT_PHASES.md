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

## Backend milestone — simulated execution and reconciliation
- `backend/demo_execution.py`: network-free demo fills, bounded adverse slippage, spread-cost estimate and process-local duplicate-request detection.
- `backend/reconciliation.py`: read-only balance/trade/position consistency checks.
- `GET /api/diagnostics/reconciliation`: diagnostic report; does not modify balances.
- `backend/test_demo_execution.py`: deterministic unit tests added, not yet executed.
- No Vercel or backend deployment requested or initiated.
- **Next critical milestone:** durable append-only ledger, atomic balance mutations and broker demo reconciliation. Existing shared MongoDB state must not be used for real capital.

## Backend milestone — transactional paper trade ledger
- Added `backend/ledger.py`: compare-and-swap state revision and newly closed paper-trade event inserts in one MongoDB transaction.
- `backend/main.py` now requires MongoDB transactions for state changes; transaction-unavailable deployments fail closed.
- Existing paper account documents without a revision field are migrated to revision 0 at startup.
- New endpoint: `GET /api/ledger/events?limit=50`.
- Added `backend/test_ledger.py` unit tests; not executed at user's request.
- Existing historical trades are **not backfilled** into the event collection; only newly closed trades produce events.
- This ledger is append-only by application convention, not tamper-proof: production requires restricted MongoDB permissions and immutable external audit storage.
- Multi-process writers now reject stale revisions, but a worker must reload after HTTP 409; concurrent in-memory readers may remain stale.
- **Next:** full event-sourced account accounting, deposit/withdrawal ledger, replay/rebuild tooling, durable broker demo idempotency, and integration tests against MongoDB Atlas transactions.
- No deployment was initiated.

## Backend milestone — durable demo intents and crash recovery
- Added `backend/demo_orders.py`: separate MongoDB `demo_order_intents` collection keyed by client order ID, with `PENDING` → `FILLED` conditional update.
- Demo order payload and slippage are pinned on first submission; repeated identical requests return the original fill, while mismatched payloads return conflict.
- Added localhost-only `POST /api/demo/orders` and `POST /api/demo/orders/recover`, plus read-only `GET /api/demo/orders/pending`.
- Added `backend/test_demo_orders.py` fake-collection tests for duplicate replay, conflict and interrupted settlement. Tests are not yet executed.
- The demo intent collection is **independent** of the existing paper account: fills do not create positions or debit balances. No external broker API is called.
- Recovery is manually triggered, bounded and only settles internal deterministic demo fills. No automatic retry of external broker requests.
- Next: audited account-ledger reconciliation and true double-entry accounting; test MongoDB failure paths, process concurrency and authorization before external exposure.
- No deployment initiated.

## Backend milestone — independent double-entry paper accounting
- `backend/accounting.py`: USD-only double-entry accounting using integer cents, five nominal accounts (CASH, CONTRIBUTED_CAPITAL, REALIZED_PNL, FEES, WITHDRAWALS), and five journal types.
- Journal entries are balanced by construction. Insufficient virtual cash blocks withdrawals, fees and realized losses.
- Account revision update and unique-ID journal insert occur in one MongoDB transaction; retries of an identical transaction ID are idempotent.
- New `POST /api/accounting/journals` (localhost-only), `GET /api/accounting/journals`, and `GET /api/accounting/reconciliation`.
- Reconciliation independently replays the complete journal, compares stored balances, checks trial balance and revision/journal count.
- Added `backend/test_accounting.py` unit tests (not executed).
- **Important isolation:** This new paper accounting ledger starts with zero balance. It is NOT synchronized with the legacy $10,000 virtual trading state, demo fills, or real bank/broker accounts. The initial virtual capital must be recorded as an explicit CAPITAL_IN entry.
- **Production blockers:** authenticated multi-user accounts, bank/broker statement matching, trusted execution-event posting, safe migration of historical paper trades, controlled correction/reversal entries, immutable audit backups, transaction integration tests, and comprehensive financial compliance review.
- No deployment initiated and no real money handled.

## Backend milestone — fetch diagnostics, paper settlement, reversals
- Frontend no longer points a hosted browser at `127.0.0.1:8000`; missing `VITE_API_URL` shows a clear backend-not-connected message and disables order actions. **A running HTTPS backend is still required** for real API connectivity; no backend was deployed.
- `backend/settlement.py` validates persisted closed-paper-trade event identity and exact-cent P&L, then books deterministic `TRADE:<trade_id>` accounting journals. Replay is idempotent and returns individual failures. New localhost-only `POST /api/accounting/settle-paper-events`.
- `REVERSAL` journal kind reverses an existing entry using the original journal ID as `reference`, preserving the original record. Double reversal is rejected; reversed cash balances cannot go negative.
- `backend/test_accounting_integration.py` adds disposable MongoDB replica-set integration tests for idempotent settlement, reversal and reconciliation. Requires `PLAYGO_TEST_MONGODB_URI` and `PLAYGO_TEST_MONGODB_DATABASE=playgo_test_...`. **Not executed**: no test MongoDB connection supplied.
- Settlement is an explicitly invoked, bounded reconciliation step rather than an automatic background worker. Initial virtual capital must be posted before realizing losses; no historical trade backfill is attempted.
- Important: the existing frontend and backend cannot communicate on the hosted website until a backend is hosted, `VITE_API_URL` is configured, and HTTPS/CORS are aligned. No deployment initiated by assistant.

## Accounting hardening milestone
- Manual `POST /api/accounting/journals` requests for `REALIZED_GAIN` and `REALIZED_LOSS` are blocked; only the dedicated persisted paper event settlement endpoint may post those journal types.
- Accounting journal P&L entries now require deterministic `TRADE:<id>` and `CLOSED:<id>` reference pairing.
- Reversals insert a unique `REVERSAL_CLAIM:<original transaction ID>` document inside the same MongoDB transaction as the reversal journal and account update. Internal claim documents are excluded from journal listing and reconciliation count.
- `GET /api/accounting/settlement-audit` compares recent persisted paper-close events with corresponding journals, reporting missing or mismatched settlements. The audit is bounded, not exhaustive.
- Existing `test_accounting.py` fixtures updated for settlement-linked IDs.
- **Security limitations:** no authentication or user isolation; paper settlement remains manual; event authenticity is based on the internal persisted paper event collection; not broker verified.
- **Testing limitations:** no live MongoDB test environment or end-to-end test results available. Do not infer correctness from commits alone.
- No deployment initiated.

## Security milestone — fail-closed private API access and CI
- `backend/access_policy.py` now gates all `/api/` endpoints and FastAPI documentation/schema routes, not only POST endpoints.
- Localhost remains available for development. Remote requests are denied by default; with `PLAYGO_ENV=local` and a 32+ character `PLAYGO_DEV_API_TOKEN`, authenticated remote reads are possible. Remote writes remain blocked regardless of token.
- **This is not user authentication.** A shared development token must not be shipped to browsers or treated as tenant isolation. No public multi-user access or live trading.
- `backend/test_access_policy.py` covers private read access, blocked writes, token validation and docs protection.
- `.github/workflows/backend-tests.yml` runs backend unittest discovery on GitHub Actions after relevant commits. Integration tests require disposable MongoDB credentials and skip when absent. CI execution/results have not been verified.
- No deployment initiated. Public frontend API connectivity is intentionally blocked until a proper authenticated, tenant-isolated backend is implemented.
- Next: implement per-user identity with server-side JWT verification and per-account document scoping; migrate the legacy shared state only after explicit review.

## Identity foundation — development-only isolated paper accounts
- Added `backend/identity.py` with PBKDF2-HMAC-SHA256 password hashing, random opaque 8-hour bearer sessions (only token SHA-256 hashes stored), session revocation and independent zero-balance per-user paper account documents.
- Added localhost-only `POST /api/identity/register`, `POST /api/identity/login`, `POST /api/identity/logout`, and `GET /api/identity/me/paper-account`.
- MongoDB unique username and user ID indexes, and TTL expiry index for session documents, are initialized on backend startup.
- Added `backend/test_identity.py` covering user separation, credential rejection, duplicate usernames, and logout. Test execution is not yet verified.
- **Not production authentication:** registration has no email verification, rate limits, MFA, session rotation, account recovery or independent security review. Never expose this development identity subsystem publicly.
- **Critical separation:** the legacy `/api/status`, trading routes, demo orders and accounting endpoints still use shared global state and are NOT per-user scoped. The new isolated accounts are deliberately read-only and start at zero. No automatic migration, and no real-money functionality.
- Existing remote API restrictions remain; the new identity routes are localhost-only under the existing policy. No deployment initiated.
- Next: refactor all trading/accounting persistence to require verified user identity and tenant-scoped queries, then implement a reviewed legacy migration and end-to-end database isolation tests.

## Architecture correction — PlayGo company-owned account (not multi-tenant)
- Trading capital and financial records belong exclusively to **PlayGo Tanzania Limited**, company key `PLAYGO_TANZANIA_LIMITED`.
- Staff members are operators within the company, not independent account holders. Roles defined: OWNER, TRADER, ACCOUNTANT, AUDITOR; role policy implemented in `backend/company.py`.
- Public `POST /api/identity/register` is disabled; company staff must be explicitly provisioned by an owner through a future secure workflow. Existing development identities do not automatically become company staff.
- Legacy `GET /api/identity/me/paper-account` now returns company staff context without creating a personal balance.
- Owner-only `GET /api/company/migration-preview` reports legacy trading state and accounting counts without writing or migrating any funds.
- `backend/test_company.py` covers company identity, role permissions, staff rejection and fail-closed migration preview.
- **Not yet complete:** role authorization is not yet enforced on all legacy trading/accounting endpoints; no company owner bootstrap or staff provisioning workflow exists; shared paper trading state remains. This is a safe architecture transition, not a completed authorization cutover.
- Do not create per-user trading accounts or auto-migrate legacy capital. No deployment initiated.

## Current operating model — single PlayGo owner + autonomous paper bots
- Exactly **one human login**, the PlayGo Tanzania Limited OWNER. No customer accounts, no staff self-registration, no separate bot identities.
- One-time localhost-only `POST /api/identity/bootstrap-owner` requires a strong `PLAYGO_OWNER_BOOTSTRAP_SECRET` (minimum 32 characters) sent via `X-PlayGo-Bootstrap-Secret` header. Keep this secret server-side; disable it after initial setup. Public `/api/identity/register` stays disabled.
- Database unique partial index on `company_id=PLAYGO_TANZANIA_LIMITED` prevents duplicate company owners even under concurrent requests.
- Owner login uses the existing `/api/identity/login` and 8-hour opaque session token. Existing legacy identities without company ownership are not automatically promoted.
- AI agents and the bot are internal software components, not users; they must operate under the single company paper account and existing risk supervisor. No live-money execution.
- **Incomplete:** the legacy trading and accounting endpoints still require owner-session authorization integration; bot lifecycle and audit attribution need review; the existing shared development trading state is not yet migrated. Do not expose publicly or deploy.
