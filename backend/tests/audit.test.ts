// audit.test.ts — Immutable audit log + trade event helpers (DB integration).
import { test, expect, describe, beforeAll, afterAll } from 'bun:test'
import { db } from '@/lib/db'
import { audit, recordTradeEvent } from '@/lib/audit'
import { ensureInstruments } from '@/lib/market'
import {
  createTestUser,
  createTestPaperAccount,
  cleanupTestAccount,
  cleanupTestUser,
  uniq,
} from './helpers'

describe('audit', () => {
  let userId: string
  let accountId: string
  let orderId: string

  beforeAll(async () => {
    await ensureInstruments()
    const u = await createTestUser(uniq('audit'))
    userId = u.id
    const a = await createTestPaperAccount(userId, 'Audit Test Account')
    accountId = a.id
    const inst = await db.instrument.findUnique({ where: { symbol: 'EUR/USD' } })
    const order = await db.order.create({
      data: {
        tradingAccountId: accountId,
        instrumentId: inst!.id,
        clientOrderId: uniq('audit-coi'),
        side: 'BUY',
        type: 'MARKET',
        size: '1',
        status: 'CREATED',
      },
    })
    orderId = order.id
  })

  afterAll(async () => {
    await cleanupTestAccount(accountId)
    await cleanupTestUser(userId)
  })

  test('audit() inserts an AuditLog row', async () => {
    const action = 'TEST_AUDIT_' + uniq('act')
    await audit({
      userId,
      action,
      entity: 'TestEntity',
      entityId: 'test-entity-1',
      after: { foo: 'bar', n: 42 },
    })
    const row = await db.auditLog.findFirst({ where: { action, userId } })
    expect(row).not.toBeNull()
    expect(row!.action).toBe(action)
    expect(row!.entity).toBe('TestEntity')
    expect(row!.entityId).toBe('test-entity-1')
    expect(row!.after).toContain('foo')
    expect(row!.after).toContain('bar')
  })

  test('recordTradeEvent() inserts a TradeEvent row linked to the order', async () => {
    const type = 'TEST_TRADE_EVENT'
    const payload = { detail: 'automated test event payload', n: 7 }
    await recordTradeEvent(orderId, type, payload)
    const row = await db.tradeEvent.findFirst({ where: { orderId, type } })
    expect(row).not.toBeNull()
    expect(row!.orderId).toBe(orderId)
    expect(row!.type).toBe(type)
    expect(row!.payload).toContain('automated test event payload')
    expect(row!.payload).toContain('7')
  })
})
