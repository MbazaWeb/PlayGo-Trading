# Database Architecture

## Datasource

- **Sandbox (this build):** SQLite via Prisma (`file:./db/custom.db`).
- **Production target:** PostgreSQL 17 (matches original PlayGo directive). The schema below maps directly; only the datasource provider changes.

## Models (17)

| Model | Role | Append-only? |
|---|---|---|
| `User` | Account owner | No |
| `Session` | DB-backed auth session | No (deleted on logout/expiry) |
| `TradingAccount` | Per-user PAPER/DEMO/LIVE account | No |
| `BrokerConnection` | Broker link + permissions | No |
| `Instrument` | Tradeable symbol metadata | No |
| `Candle` | OHLCV market data | Insert-only (unique constraint) |
| `Order` | Order record + lifecycle status | No (status transitions) |
| `Position` | Open/closed position | No |
| `AccountingJournal` | Double-entry journal header | **YES (append-only)** |
| `LedgerEntry` | Double-entry line items | **YES (append-only)** |
| `TradeEvent` | Order lifecycle audit events | **YES (append-only)** |
| `Strategy` | Strategy definition + version | No |
| `Backtest` | Backtest result archive | Insert-only |
| `RiskLimit` | Versioned risk configuration | Insert-only (prior versions retired, never mutated) |
| `EmergencyStop` | ES activation record | Insert-only |
| `AuditLog` | Immutable audit trail | **YES (append-only)** |
| `SystemHealth` | Component health checks | Insert-only |
| `Reconciliation` | Daily reconciliation record | Insert-only |

## Append-only enforcement

### Sandbox (SQLite)

SQLite does not support per-role DML grants. Append-only is enforced at the **repository layer**:

- `src/lib/accounting.ts` exposes only `postJournal()` (create) and read functions for journals/ledger.
- `src/lib/audit.ts` exposes only `recordTradeEvent()` (create) and read for trade events.
- An explicit guard `assertAppendOnly()` throws on any update/delete attempt.
- Each `AccountingJournal` stores a `integrityHash` (SHA-256 of `journalId + type + sorted entries`). On read, `verifyIntegrity()` recomputes and compares.

### Production (PostgreSQL) — DDL to apply on migration

```sql
-- Least-privilege roles
CREATE ROLE playgo_app LOGIN PASSWORD '<managed-secret>';
CREATE ROLE playgo_audit LOGIN PASSWORD '<managed-secret>';

-- Application role: INSERT + SELECT on financial tables, NO UPDATE/DELETE/TRUNCATE
GRANT SELECT, INSERT ON playgo_private.accounting_journals TO playgo_app;
GRANT SELECT, INSERT ON playgo_private.ledger_entries TO playgo_app;
GRANT SELECT, INSERT ON playgo_private.trade_events TO playgo_app;
GRANT SELECT, INSERT ON playgo_private.audit_logs TO playgo_app;
REVOKE UPDATE, DELETE, TRUNCATE ON playgo_private.accounting_journals FROM playgo_app;
REVOKE UPDATE, DELETE, TRUNCATE ON playgo_private.ledger_entries FROM playgo_app;
REVOKE UPDATE, DELETE, TRUNCATE ON playgo_private.trade_events FROM playgo_app;
REVOKE UPDATE, DELETE, TRUNCATE ON playgo_private.audit_logs FROM playgo_app;

-- Audit trigger: raise on any UPDATE/DELETE attempt (defense in depth)
CREATE OR REPLACE FUNCTION playgo_private.reject_mutation()
RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION 'APPEND-ONLY VIOLATION: % on % forbidden', TG_OP, TG_TABLE_NAME;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER no_update_journals  BEFORE UPDATE OR DELETE OR TRUNCATE ON playgo_private.accounting_journals
  FOR EACH STATEMENT EXECUTE FUNCTION playgo_private.reject_mutation();
CREATE TRIGGER no_update_events    BEFORE UPDATE OR DELETE OR TRUNCATE ON playgo_private.trade_events
  FOR EACH STATEMENT EXECUTE FUNCTION playgo_private.reject_mutation();
CREATE TRIGGER no_update_ledger    BEFORE UPDATE OR DELETE OR TRUNCATE ON playgo_private.ledger_entries
  FOR EACH STATEMENT EXECUTE FUNCTION playgo_private.reject_mutation();
```

> **Trust boundary note (per directive §A1):** Database triggers and role grants **cannot** prevent a PostgreSQL superuser or the table owner from mutating rows. The production deployment must restrict superuser/owner access to a break-glass credential used only for approved migrations. Application DB connections must use the `playgo_app` role exclusively.

## Double-entry chart of accounts

| Account type | Normal balance | Purpose |
|---|---|---|
| `CASH` | Debit | Liquid cash |
| `CAPITAL` | Credit | Owner's opening capital |
| `CLIENT_LIABILITY` | (balancing) | Offset for open positions / unrealized |
| `REALIZED_PNL` | Credit | Realized profit (credit) / loss (debit) |
| `UNREALIZED_PNL` | Credit | Mark-to-market unrealized (not currently posted; reflected in equity calc) |
| `COMMISSION` | Debit | Broker commission expense |
| `SWAP` | Debit | Financing/swap expense |
| `FEES` | Debit | Other fees |

### Balancing rule

Every journal MUST satisfy `sum(debit) === sum(credit)`. `accounting.postJournal()` calls `assertBalanced()` before any write and throws on imbalance. The browser-verified trial balance for the seeded account reads: **Debit $10001.09 = Credit $10001.09 — BALANCED**.

## Idempotency

- `AccountingJournal.ref` is `@unique`. `postJournal()` returns the existing journal if `ref` matches — startup re-runs of `postOpeningCapital()` never duplicate the opening journal.
- `Order.clientOrderId` is `@unique`. `createOrder()` returns the original order on duplicate submission.
- `Candle` has `@@unique([instrumentId, timeframe, ts])` — candle regeneration is idempotent.

## Decimal precision

All monetary Prisma fields use `Decimal` (stored as TEXT in SQLite, returned as decimal.js objects). Rounding uses `ROUND_HALF_UP` at precision 28. Currency values round to 2dp; prices round to the instrument's `pipSize`.
