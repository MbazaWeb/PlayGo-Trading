// helpers.ts — Shared test utilities for the PlayGo Trading test suite.
//
// Every DB-writing test creates its own throwaway data with unique identifiers
// and cleans it up in afterAll to avoid polluting the seeded demo data.
import { db } from '@/lib/db'

// Unique identifier generator (timestamp + random — no dependency on mocked Date).
export function uniq(prefix: string): string {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`
}

// Create a throwaway test user with a dummy password hash (never logged in).
export async function createTestUser(suffix: string): Promise<{ id: string; email: string }> {
  const u = await db.user.create({
    data: {
      email: `test-${suffix}@playgo.local`,
      name: `Test ${suffix}`,
      // Dummy hash — these users are never authenticated against.
      passwordHash: 'test-dummy-hash-not-real-bcrypt',
      role: 'USER',
    },
  })
  return { id: u.id, email: u.email }
}

// Create a throwaway PAPER trading account.
export async function createTestPaperAccount(userId: string, label: string): Promise<{ id: string }> {
  const acc = await db.tradingAccount.create({
    data: {
      userId,
      label,
      mode: 'PAPER',
      broker: 'PAPER',
      currency: 'USD',
      liveAuthorized: false,
    },
  })
  return { id: acc.id }
}

// Delete a trading account and all of its dependent rows in the correct order
// to respect FK constraints (notably LedgerEntry.journal is onDelete: Restrict,
// so entries must be removed before journals).
export async function cleanupTestAccount(accountId: string): Promise<void> {
  // 1. Ledger entries -> journals (Restrict)
  const journalIds = (
    await db.accountingJournal.findMany({
      where: { tradingAccountId: accountId },
      select: { id: true },
    })
  ).map((j) => j.id)
  if (journalIds.length) {
    await db.ledgerEntry.deleteMany({ where: { journalId: { in: journalIds } } })
  }
  await db.accountingJournal.deleteMany({ where: { tradingAccountId: accountId } })

  // 2. Trade events -> orders (Cascade, but delete explicitly for ordering safety)
  const orderIds = (
    await db.order.findMany({
      where: { tradingAccountId: accountId },
      select: { id: true },
    })
  ).map((o) => o.id)
  if (orderIds.length) {
    await db.tradeEvent.deleteMany({ where: { orderId: { in: orderIds } } })
  }
  await db.order.deleteMany({ where: { tradingAccountId: accountId } })

  // 3. Remaining dependents
  await db.position.deleteMany({ where: { tradingAccountId: accountId } })
  await db.riskLimit.deleteMany({ where: { tradingAccountId: accountId } })
  await db.emergencyStop.deleteMany({ where: { tradingAccountId: accountId } })
  await db.brokerConnection.deleteMany({ where: { tradingAccountId: accountId } })
  await db.tradingAccount.deleteMany({ where: { id: accountId } })
}

// Delete a test user and any audit logs / sessions it owns.
export async function cleanupTestUser(userId: string): Promise<void> {
  await db.auditLog.deleteMany({ where: { userId } })
  await db.session.deleteMany({ where: { userId } })
  await db.user.deleteMany({ where: { id: userId } })
}
