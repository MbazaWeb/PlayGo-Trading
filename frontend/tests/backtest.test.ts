// backtest.test.ts — Strategy backtesting engine (DB integration).
import { test, expect, describe, beforeAll, afterAll } from 'bun:test'
import { db } from '@/lib/db'
import { runBacktest, type BacktestResult } from '@/lib/backtest'
import { ensureInstruments } from '@/lib/market'
import { uniq } from './helpers'

describe('backtest', () => {
  let strategyId: string
  // An isolated historical range used only by this test file.
  const from = new Date('2025-05-01T00:00:00Z')
  const to = new Date('2025-05-31T00:00:00Z')
  const params = {
    fastPeriod: 10,
    slowPeriod: 30,
    stopLossPips: 20,
    takeProfitPips: 40,
    size: 1,
  }

  beforeAll(async () => {
    await ensureInstruments()
    const strat = await db.strategy.create({
      data: {
        name: 'Test MA Cross ' + uniq('strat'),
        version: 1,
        description: 'Test strategy for the automated test suite',
        entryRules: JSON.stringify({ fastCrossAboveSlow: 'BUY', fastCrossBelowSlow: 'SELL' }),
        exitRules: JSON.stringify({ stopLossPips: 20, takeProfitPips: 40 }),
        positionSizing: JSON.stringify({ fixedSize: 1 }),
        instruments: 'EUR/USD',
        timeframes: 'M15',
        maxDrawdownPct: 20,
        status: 'VALIDATED',
      },
    })
    strategyId = strat.id
  })

  afterAll(async () => {
    // Deleting the strategy cascades its backtests.
    await db.strategy.deleteMany({ where: { id: strategyId } })
  })

  function assertAllMetricsPresent(r: BacktestResult) {
    // The 12 core metric fields
    expect(typeof r.netReturn).toBe('string')
    expect(typeof r.maxDrawdown).toBe('string')
    expect(typeof r.sharpe).toBe('number')
    expect(typeof r.sortino).toBe('number')
    expect(typeof r.calmar).toBe('number')
    expect(typeof r.winRate).toBe('number')
    expect(typeof r.profitFactor).toBe('number')
    expect(typeof r.expectancy).toBe('string')
    expect(typeof r.avgGain).toBe('string')
    expect(typeof r.avgLoss).toBe('string')
    expect(typeof r.exposure).toBe('number')
    expect(typeof r.trades).toBe('number')
    // Supporting fields
    expect(typeof r.netReturnPct).toBe('string')
    expect(typeof r.maxDrawdownPct).toBe('string')
    expect(typeof r.turnover).toBe('string')
    expect(typeof r.transactionCosts).toBe('string')
    expect(Array.isArray(r.equityCurve)).toBe(true)
    expect(Array.isArray(r.warnings)).toBe(true)
  }

  test('runBacktest returns a BacktestResult with all 12 metric fields and equityCurve array', async () => {
    const r = await runBacktest({
      strategyId,
      instrument: 'EUR/USD',
      timeframe: 'M15',
      fromDate: from,
      toDate: to,
      params,
    })
    assertAllMetricsPresent(r)
    expect(r.trades).toBeGreaterThanOrEqual(0)
    // Backtest row persisted
    const rows = await db.backtest.count({ where: { strategyId } })
    expect(rows).toBeGreaterThanOrEqual(1)
  })

  test('determinism: identical params on the same range yield the same netReturn and trades count', async () => {
    const r1 = await runBacktest({
      strategyId,
      instrument: 'EUR/USD',
      timeframe: 'M15',
      fromDate: from,
      toDate: to,
      params,
    })
    const r2 = await runBacktest({
      strategyId,
      instrument: 'EUR/USD',
      timeframe: 'M15',
      fromDate: from,
      toDate: to,
      params,
    })
    expect(r2.trades).toBe(r1.trades)
    expect(r2.netReturn).toBe(r1.netReturn)
    expect(r2.equityCurve.length).toBe(r1.equityCurve.length)
  })
})
