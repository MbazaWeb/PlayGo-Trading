// market.test.ts — Synthetic market data engine (DB integration).
import { test, expect, describe, beforeAll, afterAll } from 'bun:test'
import { db } from '@/lib/db'
import {
  ensureInstruments,
  getCandles,
  getQuote,
  listInstruments,
  tfSeconds,
  INSTRUMENTS,
} from '@/lib/market'
import { D } from '@/lib/money'

describe('market', () => {
  let eurUsdId: string
  // A small, isolated historical range used only by this test file.
  const from = new Date('2025-04-01T00:00:00Z')
  const to = new Date('2025-04-02T00:00:00Z')

  beforeAll(async () => {
    await ensureInstruments()
    const inst = await db.instrument.findUnique({ where: { symbol: 'EUR/USD' } })
    eurUsdId = inst!.id
  })

  afterAll(async () => {
    // Delete generated candles for the test range — but NOT the instrument definitions.
    await db.candle.deleteMany({
      where: { instrumentId: eurUsdId, timeframe: 'M15', ts: { gte: from, lte: to } },
    })
  })

  test('INSTRUMENTS exports all 8 instruments', () => {
    expect(INSTRUMENTS).toHaveLength(8)
    expect(INSTRUMENTS.map((i) => i.symbol)).toContain('EUR/USD')
  })

  test('ensureInstruments upserts all 8; EUR/USD exists with kind FOREX', async () => {
    await ensureInstruments()
    const list = await listInstruments()
    expect(list.length).toBeGreaterThanOrEqual(8)
    const eur = list.find((i) => i.symbol === 'EUR/USD')
    expect(eur).toBeDefined()
    expect(eur!.kind).toBe('FOREX')
    expect(eur!.pipSize).toBe('0.0001')
  })

  test('tfSeconds maps timeframes correctly', () => {
    expect(tfSeconds('M1')).toBe(60)
    expect(tfSeconds('M5')).toBe(300)
    expect(tfSeconds('M15')).toBe(900)
    expect(tfSeconds('H1')).toBe(3600)
    expect(tfSeconds('H4')).toBe(14400)
    expect(tfSeconds('D1')).toBe(86400)
  })

  test('getCandles returns candles; calling twice returns the SAME candles (idempotent, no duplicates)', async () => {
    const c1 = await getCandles('EUR/USD', 'M15', from, to)
    expect(c1.length).toBeGreaterThan(0)
    const c2 = await getCandles('EUR/USD', 'M15', from, to)
    expect(c2.length).toBe(c1.length)
    // Identical content
    for (let i = 0; i < c1.length; i++) {
      expect(c2[i].ts.toISOString()).toBe(c1[i].ts.toISOString())
      expect(c2[i].open).toBe(c1[i].open)
      expect(c2[i].high).toBe(c1[i].high)
      expect(c2[i].low).toBe(c1[i].low)
      expect(c2[i].close).toBe(c1[i].close)
      expect(c2[i].volume).toBe(c1[i].volume)
    }
    // No duplicate rows persisted
    const dbCount = await db.candle.count({
      where: { instrumentId: eurUsdId, timeframe: 'M15', ts: { gte: from, lte: to } },
    })
    expect(dbCount).toBe(c1.length)
  })

  test('getQuote returns {bid, ask, mid, spread, isPaper:true, source:synthetic}; ask > bid', async () => {
    const q = await getQuote('EUR/USD')
    expect(q.symbol).toBe('EUR/USD')
    expect(q.isPaper).toBe(true)
    expect(q.source).toBe('synthetic')
    expect(D(q.ask).gt(D(q.bid))).toBe(true)
    expect(D(q.mid).gt(0)).toBe(true)
    expect(D(q.spread).gt(0)).toBe(true)
  })
})
