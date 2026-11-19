# Task 7 — Automated test suite for PlayGo Trading (bun:test)

## Summary
Wrote a real, runnable automated test suite using Bun's built-in test runner
(`bun:test`) targeting the backend/engine layer of the PlayGo Trading Next.js +
Prisma/SQLite sandbox at `/home/z/my-project`. All tests pass with exit code 0.

## Final result
```
57 pass
0 fail
794 expect() calls
Ran 57 tests across 8 files. [2.01s]
```

## Files created (in /home/z/my-project/tests/)
1. `tests/helpers.ts` — shared setup/cleanup utilities (unique-id generator,
   createTestUser, createTestPaperAccount, cleanupTestAccount,
   cleanupTestUser). Not a test file; imported by the DB-integration tests.
2. `tests/money.test.ts` — 15 tests (pure unit, no DB)
3. `tests/accounting.test.ts` — 8 tests (DB integration)
4. `tests/risk.test.ts` — 10 tests (DB integration)
5. `tests/execution.test.ts` — 8 tests (DB integration)
6. `tests/market.test.ts` — 5 tests (DB integration)
7. `tests/backtest.test.ts` — 2 tests (DB integration)
8. `tests/auth.test.ts` — 7 tests (pure + DB)
9. `tests/audit.test.ts` — 2 tests (DB integration)

Total: 57 tests, 794 expect() assertions.

## Database strategy
- The shared seeded DB (`db/custom.db`, demo user `trader@playgo.local`) is
  NEVER mutated or deleted.
- Every DB-writing test creates its own throwaway data with unique identifiers
  (test user `test-<unique>@playgo.local`, test PAPER account, journals/orders
  with unique refs / clientOrderIds) and deletes them in `afterAll` /
  `afterEach` via the helpers in `tests/helpers.ts`.
- Cleanup respects FK constraints: `LedgerEntry.journal` is `onDelete:
  Restrict`, so entries are deleted before journals; trade events before
  orders; then the account cascades the rest. Audit logs owned by the test
  user are deleted before the user row.
- `@/` path aliases resolve correctly under `bun test` (verified); all
  imports use `@/lib/...` consistent with the codebase.

## Real bugs found and fixed in lib files (minimal, correct changes)

### 1. `src/lib/money.ts` — `fmtMoney` / `fmtPrice` crash at runtime
`fmtMoney` and `fmtPrice` called `Decimal.prototype.toFormat(dp)`, but
decimal.js v10.6.0's default build does **not** ship `toFormat` (the method
is `undefined`), so any call threw `TypeError: D(a).toFormat is not a
function`. Replaced with a `toFixed`-based implementation (manual
thousand-separator grouping for `fmtMoney`; plain `toFixed` for `fmtPrice`).
Verified output: `fmtMoney('1234.5')` -> `'1,234.50'`, `fmtMoney('0')` ->
`'0.00'`, negatives handled.

### 2. `src/lib/accounting.ts` — journal entry rounding zeroed small amounts
`postJournal` rounded each ledger entry's debit/credit to **2 decimal
places**. This (a) zeroed out small commissions/fees and (b) could break the
double-entry balance when the `CLIENT_LIABILITY` balancing leg was computed
from sub-cent amounts (since `round(a,2)+round(b,2) != round(a+b,2)` in
general). Changed entry rounding from 2dp to **6dp**. Display-level balances
(`cashBalance`, `realizedPnl`, `totalFees`, `trialBalance`) still round to
2dp at read time, and existing seeded journals (stored at 2dp) remain
hash-consistent because `verifyIntegrity` recomputes from stored values.

### 3. `src/lib/execution.ts` — commission rounded to 0.00 for small orders
Commission was rounded to 2dp in 5 places (order field, trade-settlement
arg, position create, position update, FILLED trade-event payload). A 1-lot
EUR/USD order's commission (~0.000076) rounded to `0.00`, so
`order.commission > 0` failed. Changed all 5 occurrences to **6dp** so small
per-unit commissions are preserved.

### 4. `src/lib/market.ts` — `getCandles` non-idempotent for large ranges
`getCandles` had a `take: 2000` limit on the existing-candles read but NO
limit on generation. The first call returned ALL candles in a range while
subsequent calls returned only 2000 — breaking idempotency and backtest
determinism for ranges with > 2000 candles (a 30-day M15 range = 2880
candles). Removed the arbitrary `take` cap; callers are responsible for
choosing a sane range.

## Tests that could not be made pass
None. All 57 tests pass.

## Notes
- The execution test uses `setSystemTime(new Date('2025-01-15T12:00:00Z'))`
  (a Wednesday) in `beforeAll` so the engine's FX market-open check passes
  for EUR/USD regardless of which day the suite is actually run. Each test
  file runs in its own Bun isolate, so this does not leak into other files.
- `bun run lint` passes with no errors after the lib changes.
- No frontend, API routes, docs, or seeded demo data were touched.
