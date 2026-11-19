// execution.test.ts — Paper execution engine (DB integration).
import { test, expect, describe, beforeAll, afterAll, setSystemTime } from 'bun:test'
import { Decimal } from 'decimal.js'
import { db } from '@/lib/db'
import {
  createOrder,
  closePosition,
  genClientOrderId,
  getTradingAccount,
} from '@/lib/execution'
import { ensureInstruments } from '@/lib/market'
import { postOpeningCapital } from '@/lib/accounting'
import { D } from '@/lib/money'
import {
  createTestUser,
  createTestPaperAccount,
  cleanupTestAccount,
  cleanupTestUser,
  uniq,
} from './helpers'

describe('execution', () => {
  let userId: string
  let accountId: string
  let realNow: () => Date

  beforeAll(async () => {
    // Force a weekday so the FX market-open check passes for EUR/USD.
    // (FX is closed Saturday and Sunday-before-22:00 UTC in the engine.)
    setSystemTime(new Date('2025-01-15T12:00:00Z')) // Wednesday
    await ensureInstruments()
    const u = await createTestUser(uniq('exec'))
    userId = u.id
    const a = await createTestPaperAccount(userId, 'Execution Test Account')
    accountId = a.id
    await postOpeningCapital(accountId, '10000.00', userId)
    await db.riskLimit.create({
      data: {
        tradingAccountId: accountId,
        version: 1,
        maxPositionSize: '10',
        maxLeverage: '30',
        maxDailyLossPct: '5',
        maxWeeklyLossPct: '10',
        maxDrawdownPct: '20',
        maxAggregateExposure: '50000',
        maxSimultaneousPositions: 10,
        maxSpreadPips: '5',
        maxSlippagePips: '3',
        active: true,
      },
    })
  })

  afterAll(async () => {
    await cleanupTestAccount(accountId)
    await cleanupTestUser(userId)
    setSystemTime(new Date())
  })

  test('getTradingAccount returns the owned account', async () => {
    const acc = await getTradingAccount(accountId, userId)
    expect(acc.id).toBe(accountId)
    await expect(getTradingAccount(accountId, 'nonexistent-user')).rejects.toThrow(/not found/)
  })

  test('genClientOrderId returns a unique "C"-prefixed hex string', () => {
    const a = genClientOrderId()
    const b = genClientOrderId()
    expect(a).toMatch(/^C[0-9a-f]{24}$/)
    expect(b).toMatch(/^C[0-9a-f]{24}$/)
    expect(a).not.toBe(b)
  })

  test('createOrder BUY 1 EUR/USD -> FILLED, filledSize==1, avgFillPrice set, commission>0', async () => {
    const coi = genClientOrderId()
    const res = await createOrder({
      tradingAccountId: accountId,
      userId,
      clientOrderId: coi,
      symbol: 'EUR/USD',
      side: 'BUY',
      type: 'MARKET',
      size: '1',
    })
    const order = res.order!
    expect(order.status).toBe('FILLED')
    expect(D(order.filledSize).eq(new Decimal(1))).toBe(true)
    expect(order.avgFillPrice).not.toBeNull()
    expect(D(order.avgFillPrice!).gt(0)).toBe(true)
    expect(D(order.commission).gt(0)).toBe(true)
  })

  test('idempotency: same clientOrderId returns idempotent:true, no new order', async () => {
    const coi = genClientOrderId()
    const res1 = await createOrder({
      tradingAccountId: accountId,
      userId,
      clientOrderId: coi,
      symbol: 'EUR/USD',
      side: 'BUY',
      type: 'MARKET',
      size: '1',
    })
    const res2 = await createOrder({
      tradingAccountId: accountId,
      userId,
      clientOrderId: coi,
      symbol: 'EUR/USD',
      side: 'BUY',
      type: 'MARKET',
      size: '1',
    })
    expect(res2.idempotent).toBe(true)
    expect(res2.order!.id).toBe(res1.order!.id)
    const count = await db.order.count({ where: { clientOrderId: coi } })
    expect(count).toBe(1)
  })

  test('order with size 0 throws', async () => {
    await expect(
      createOrder({
        tradingAccountId: accountId,
        userId,
        clientOrderId: genClientOrderId(),
        symbol: 'EUR/USD',
        side: 'BUY',
        type: 'MARKET',
        size: '0',
      })
    ).rejects.toThrow(/positive/)
  })

  test('order with oversized size -> REJECTED status with rejectReason', async () => {
    const coi = genClientOrderId()
    const res = await createOrder({
      tradingAccountId: accountId,
      userId,
      clientOrderId: coi,
      symbol: 'EUR/USD',
      side: 'BUY',
      type: 'MARKET',
      size: '20', // exceeds maxPositionSize=10 but <= instrument maxSize=100
    })
    const order = res.order!
    expect(order.status).toBe('REJECTED')
    expect(order.rejectReason).not.toBeNull()
    expect(order.rejectReason!.length).toBeGreaterThan(0)
  })

  test('trade events: at least 6 events recorded for a filled order', async () => {
    const coi = genClientOrderId()
    const res = await createOrder({
      tradingAccountId: accountId,
      userId,
      clientOrderId: coi,
      symbol: 'EUR/USD',
      side: 'BUY',
      type: 'MARKET',
      size: '1',
    })
    const events = await db.tradeEvent.findMany({
      where: { orderId: res.order!.id },
      orderBy: { createdAt: 'asc' },
    })
    expect(events.length).toBeGreaterThanOrEqual(6)
    const types = events.map((e) => e.type)
    for (const t of ['CREATED', 'VALIDATED', 'RISK_APPROVED', 'SUBMITTED', 'ACCEPTED', 'FILLED']) {
      expect(types).toContain(t)
    }
  })

  test('position keeps the order stop-loss and take-profit', async () => {
    await createOrder({
      tradingAccountId: accountId,
      userId,
      clientOrderId: genClientOrderId(),
      symbol: 'EUR/USD',
      side: 'BUY',
      type: 'MARKET',
      size: '1',
      stopLoss: '1.0500',
      takeProfit: '1.1200',
    })
    const position = await db.position.findFirst({
      where: { tradingAccountId: accountId, status: 'OPEN' },
    })
    expect(position?.stopLoss?.toString()).toBe('1.05')
    expect(position?.takeProfit?.toString()).toBe('1.12')
  })

  test('position opened; closePosition -> CLOSED, realizedPnl recorded', async () => {
    // Find the open position created by the earlier FILLED BUY orders.
    const pos = await db.position.findFirst({
      where: { tradingAccountId: accountId, status: 'OPEN' },
    })
    expect(pos).not.toBeNull()
    const result = await closePosition(pos!.id, 'manual')
    expect(result.reason).toBe('manual')
    expect(typeof result.realizedPnl).toBe('string')
    const closed = await db.position.findUnique({ where: { id: pos!.id } })
    expect(closed!.status).toBe('CLOSED')
    expect(closed!.closedAt).not.toBeNull()
    // realizedPnl recorded as a finite decimal
    expect(D(closed!.realizedPnl).isFinite()).toBe(true)
  })
})
