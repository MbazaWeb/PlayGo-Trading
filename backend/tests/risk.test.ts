// risk.test.ts — Risk engine (DB integration).
import { test, expect, describe, beforeAll, afterAll } from 'bun:test'
import { Decimal } from 'decimal.js'
import { db } from '@/lib/db'
import {
  checkOrderRisk,
  getActiveRiskLimits,
  riskUtilization,
  type RiskContext,
} from '@/lib/risk'
import {
  activateEmergencyStop,
  deactivateEmergencyStop,
  getEmergencyStopState,
} from '@/lib/emergency'
import { postOpeningCapital } from '@/lib/accounting'
import { ensureInstruments } from '@/lib/market'
import {
  createTestUser,
  createTestPaperAccount,
  cleanupTestAccount,
  cleanupTestUser,
  uniq,
} from './helpers'

describe('risk', () => {
  let userId: string
  let accountId: string
  let eurUsdId: string

  beforeAll(async () => {
    await ensureInstruments()
    const u = await createTestUser(uniq('risk'))
    userId = u.id
    const a = await createTestPaperAccount(userId, 'Risk Test Account')
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
        maxAggregateExposure: '5000',
        maxSimultaneousPositions: 3,
        maxSpreadPips: '5',
        maxSlippagePips: '3',
        active: true,
      },
    })
    const inst = await db.instrument.findUnique({ where: { symbol: 'EUR/USD' } })
    eurUsdId = inst!.id
  })

  afterAll(async () => {
    await cleanupTestAccount(accountId)
    await cleanupTestUser(userId)
  })

  function baseCtx(overrides: Partial<RiskContext> = {}): RiskContext {
    return {
      tradingAccountId: accountId,
      mode: 'PAPER',
      liveAuthorized: false,
      symbol: 'EUR/USD',
      side: 'BUY',
      size: new Decimal(1),
      price: new Decimal('1.0850'),
      spread: new Decimal('0.00008'), // 0.8 pips
      pipSize: new Decimal('0.0001'),
      accountCurrency: 'USD',
      ...overrides,
    }
  }

  test('getActiveRiskLimits returns the configured (non-defaulted) limits', async () => {
    const limits = await getActiveRiskLimits(accountId)
    expect(limits._defaulted).toBe(false)
    expect(limits.maxPositionSize.eq(new Decimal(10))).toBe(true)
    expect(limits.maxAggregateExposure.eq(new Decimal(5000))).toBe(true)
    expect(limits.maxSimultaneousPositions).toBe(3)
  })

  test('checkOrderRisk approves a small BUY (size 1, EUR/USD) when no emergency stop', async () => {
    const r = await checkOrderRisk(baseCtx())
    expect(r.approved).toBe(true)
    expect(r.reasons).toHaveLength(0)
  })

  test('emergency stop active -> checkOrderRisk REJECTS with "Emergency stop" reason', async () => {
    await activateEmergencyStop(accountId, userId, 'test emergency stop')
    const state = await getEmergencyStopState(accountId)
    expect(state.active).toBe(true)
    const r = await checkOrderRisk(baseCtx())
    expect(r.approved).toBe(false)
    expect(r.reasons.some((x) => x.includes('Emergency stop'))).toBe(true)
  })

  test('deactivate -> approves again', async () => {
    await deactivateEmergencyStop(accountId, userId)
    const state = await getEmergencyStopState(accountId)
    expect(state.active).toBe(false)
    const r = await checkOrderRisk(baseCtx())
    expect(r.approved).toBe(true)
  })

  test('max position size: size > maxPositionSize -> rejects', async () => {
    const r = await checkOrderRisk(baseCtx({ size: new Decimal(20) }))
    expect(r.approved).toBe(false)
    expect(r.reasons.some((x) => x.toLowerCase().includes('position size'))).toBe(true)
  })

  test('max aggregate exposure: huge size -> rejects', async () => {
    const r = await checkOrderRisk(baseCtx({ size: new Decimal(10000) }))
    expect(r.approved).toBe(false)
    expect(r.reasons.some((x) => x.toLowerCase().includes('aggregate exposure'))).toBe(true)
  })

  test('max simultaneous positions: open N+1 positions -> rejects', async () => {
    // maxSimultaneousPositions = 3; create 3 dummy OPEN positions to hit the cap.
    for (let i = 0; i < 3; i++) {
      await db.position.create({
        data: {
          tradingAccountId: accountId,
          instrumentId: eurUsdId,
          side: 'BUY',
          size: '0.01',
          entryPrice: '1.0850',
          currentPrice: '1.0850',
          unrealizedPnl: '0',
          realizedPnl: '0',
          swap: '0',
          commission: '0',
          status: 'OPEN',
        },
      })
    }
    const r = await checkOrderRisk(baseCtx({ size: new Decimal(1) }))
    expect(r.approved).toBe(false)
    expect(r.reasons.some((x) => x.toLowerCase().includes('simultaneous'))).toBe(true)
    // Cleanup dummy positions so later tests see a clean state.
    await db.position.deleteMany({ where: { tradingAccountId: accountId, status: 'OPEN' } })
  })

  test('LIVE gate: mode=LIVE, liveAuthorized=false -> rejects with LIVE reason', async () => {
    const r = await checkOrderRisk(baseCtx({ mode: 'LIVE', liveAuthorized: false }))
    expect(r.approved).toBe(false)
    expect(r.reasons.some((x) => x.includes('LIVE'))).toBe(true)
    const liveCheck = r.checks.find((c) => c.name === 'live_authorization')
    expect(liveCheck?.ok).toBe(false)
  })

  test('LIVE gate: liveAuthorized=true (in memory on context) -> passes the LIVE check', async () => {
    const r = await checkOrderRisk(baseCtx({ mode: 'LIVE', liveAuthorized: true }))
    const liveCheck = r.checks.find((c) => c.name === 'live_authorization')
    expect(liveCheck?.ok).toBe(true)
    expect(r.reasons.some((x) => x.includes('LIVE'))).toBe(false)
    expect(r.approved).toBe(true)
  })

  test('riskUtilization returns a sane snapshot', async () => {
    const util = await riskUtilization(accountId)
    expect(util.defaulted).toBe(false)
    expect(util.openPositions).toBe(0)
    expect(util.exposureUtilizationPct).toBeGreaterThanOrEqual(0)
    expect(util.cash.eq(new Decimal(10000))).toBe(true)
  })
})
