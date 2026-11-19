// market.ts — Synthetic market data engine.
//
// The directive requires clearly-identified synthetic/PAPER data. This module
// generates deterministic-but-realistic forex & synthetic-index candles using
// a seeded geometric-brownian-motion model so backtests are reproducible.
//
// No real broker connection is used. In PAPER mode this is the only feed.
import { Decimal } from 'decimal.js'
import { db } from '@/lib/db'
import { D, toPip, round } from '@/lib/money'

export type InstrumentDef = {
  symbol: string
  kind: 'FOREX' | 'SYNTHETIC' | 'INDEX'
  base?: string
  quote?: string
  pipSize: string
  minSize: string
  maxSize: string
  precision: number
  description: string
  // synthetic model params
  basePrice: number
  annualVol: number // e.g. 0.08 = 8%
  drift: number // e.g. 0.0
  spreadPips: number
}

// A curated, clearly-labeled PAPER instrument universe.
export const INSTRUMENTS: InstrumentDef[] = [
  { symbol: 'EUR/USD', kind: 'FOREX', base: 'EUR', quote: 'USD', pipSize: '0.0001', minSize: '0.01', maxSize: '100', precision: 5, description: 'Euro vs US Dollar (synthetic PAPER feed)', basePrice: 1.0850, annualVol: 0.08, drift: 0.0, spreadPips: 0.8 },
  { symbol: 'GBP/USD', kind: 'FOREX', base: 'GBP', quote: 'USD', pipSize: '0.0001', minSize: '0.01', maxSize: '100', precision: 5, description: 'Pound vs US Dollar (synthetic PAPER feed)', basePrice: 1.2650, annualVol: 0.09, drift: 0.0, spreadPips: 1.0 },
  { symbol: 'USD/JPY', kind: 'FOREX', base: 'USD', quote: 'JPY', pipSize: '0.01', minSize: '0.01', maxSize: '100', precision: 3, description: 'US Dollar vs Japanese Yen (synthetic PAPER feed)', basePrice: 151.20, annualVol: 0.10, drift: 0.0, spreadPips: 1.2 },
  { symbol: 'AUD/USD', kind: 'FOREX', base: 'AUD', quote: 'USD', pipSize: '0.0001', minSize: '0.01', maxSize: '100', precision: 5, description: 'Aussie vs US Dollar (synthetic PAPER feed)', basePrice: 0.6580, annualVol: 0.11, drift: 0.0, spreadPips: 1.1 },
  { symbol: 'R_100', kind: 'SYNTHETIC', pipSize: '0.0001', minSize: '0.1', maxSize: '1000', precision: 4, description: 'Volatility 100 Index (synthetic PAPER feed)', basePrice: 1450.0, annualVol: 1.2, drift: 0.0, spreadPips: 2.0 },
  { symbol: 'R_75', kind: 'SYNTHETIC', pipSize: '0.0001', minSize: '0.1', maxSize: '1000', precision: 4, description: 'Volatility 75 Index (synthetic PAPER feed)', basePrice: 380.0, annualVol: 0.9, drift: 0.0, spreadPips: 3.0 },
  { symbol: 'BOOM_500', kind: 'SYNTHETIC', pipSize: '0.001', minSize: '0.1', maxSize: '500', precision: 3, description: 'Boom 500 Index (synthetic PAPER feed)', basePrice: 12000.0, annualVol: 0.5, drift: 0.05, spreadPips: 5.0 },
  { symbol: 'CRASH_500', kind: 'SYNTHETIC', pipSize: '0.001', minSize: '0.1', maxSize: '500', precision: 3, description: 'Crash 500 Index (synthetic PAPER feed)', basePrice: 9000.0, annualVol: 0.5, drift: -0.05, spreadPips: 5.0 },
]

export async function ensureInstruments(): Promise<void> {
  for (const def of INSTRUMENTS) {
    await db.instrument.upsert({
      where: { symbol: def.symbol },
      create: {
        symbol: def.symbol, kind: def.kind, base: def.base, quote: def.quote,
        pipSize: def.pipSize, minSize: def.minSize, maxSize: def.maxSize,
        precision: def.precision, description: def.description,
      },
      update: {
        kind: def.kind, base: def.base, quote: def.quote,
        pipSize: def.pipSize, minSize: def.minSize, maxSize: def.maxSize,
        precision: def.precision, description: def.description,
      },
    })
  }
}

// Deterministic PRNG (mulberry32) so backtest replay is reproducible.
function mulberry32(seed: number) {
  let a = seed >>> 0
  return function () {
    a |= 0; a = (a + 0x6D2B79F5) | 0
    let t = Math.imul(a ^ (a >>> 15), 1 | a)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

function hashSeed(s: string): number {
  let h = 2166136261
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i)
    h = Math.imul(h, 16777619)
  }
  return h >>> 0
}

// Generate (or fetch) a candle series for `symbol` between [from, to] on `timeframe`.
// If candles already exist in the DB for the range, we return them (idempotent).
export async function getCandles(symbol: string, timeframe: string, from: Date, to: Date) {
  const inst = await db.instrument.findUnique({ where: { symbol } })
  if (!inst) throw new Error('Unknown instrument: ' + symbol)
  // No `take` limit: capping the existing-candle read at an arbitrary number
  // (e.g. 2000) made getCandles non-idempotent for ranges larger than the cap
  // (first call returned all generated candles, subsequent calls returned only
  // the capped subset), which broke backtest determinism. Callers are
  // responsible for choosing a sane range.
  const existing = await db.candle.findMany({
    where: { instrumentId: inst.id, timeframe, ts: { gte: from, lte: to } },
    orderBy: { ts: 'asc' },
  })
  if (existing.length > 0) {
    return existing.map(c => ({
      ts: c.ts, open: c.open.toString(), high: c.high.toString(),
      low: c.low.toString(), close: c.close.toString(), volume: c.volume.toString(),
    }))
  }
  // Generate deterministically.
  const def = INSTRUMENTS.find(d => d.symbol === symbol)
  if (!def) throw new Error('Instrument def missing: ' + symbol)
  const tfSec = tfSeconds(timeframe)
  const candles = generateSeries(def, from.getTime(), to.getTime(), tfSec)
  // Persist (idempotent via the existing-candles check above + unique constraint).
  // Note: Prisma SQLite createMany does not support skipDuplicates, so we rely on
  // the pre-check and the unique([instrumentId, timeframe, ts]) constraint.
  try {
    await db.candle.createMany({
      data: candles.map(c => ({
        instrumentId: inst.id, timeframe, ts: new Date(c.ts),
        open: c.open, high: c.high, low: c.low, close: c.close, volume: c.volume,
        source: 'synthetic',
      })),
    })
  } catch (e) {
    // Unique constraint violation on concurrent runs is acceptable — the caller
    // will re-read existing candles on the next invocation.
    if (!String(e).includes('Unique constraint')) console.error('[market] candle createMany failed', e)
  }
  return candles.map(c => ({
    ts: new Date(c.ts), open: c.open.toString(), high: c.high.toString(),
    low: c.low.toString(), close: c.close.toString(), volume: c.volume.toString(),
  }))
}

export function tfSeconds(tf: string): number {
  switch (tf) {
    case 'M1': return 60
    case 'M5': return 300
    case 'M15': return 900
    case 'H1': return 3600
    case 'H4': return 14400
    case 'D1': return 86400
    default: return 60
  }
}

type RawCandle = { ts: number; open: string; high: string; low: string; close: string; volume: string }

function generateSeries(def: InstrumentDef, fromMs: number, toMs: number, tfSec: number): RawCandle[] {
  const seed = hashSeed(def.symbol)
  const rng = mulberry32(seed)
  const dtYear = tfSec / (365 * 24 * 3600)
  const sigma = def.annualVol * Math.sqrt(dtYear)
  const drift = (def.drift - 0.5 * def.annualVol * def.annualVol) * dtYear
  let price = def.basePrice
  const out: RawCandle[] = []
  for (let t = Math.floor(fromMs / 1000 / tfSec) * tfSec * 1000; t <= toMs; t += tfSec * 1000) {
    const open = price
    // GBM step
    const z = normInv(rng())
    let close = open * Math.exp(drift + sigma * z)
    if (close <= 0) close = open * 0.99
    const hi = Math.max(open, close) * (1 + Math.abs(normInv(rng())) * sigma * 0.5)
    const lo = Math.min(open, close) * (1 - Math.abs(normInv(rng())) * sigma * 0.5)
    const vol = (100 + rng() * 500).toFixed(0)
    const pip = parseFloat(def.pipSize)
    const pipStr = def.pipSize
    out.push({
      ts: t,
      open: toPip(open, pipStr).toString(),
      high: toPip(hi, pipStr).toString(),
      low: toPip(lo, pipStr).toString(),
      close: toPip(close, pipStr).toString(),
      volume: vol,
    })
    price = close
    // keep series bounded
    if (price > def.basePrice * 5) price = def.basePrice
    if (price < def.basePrice * 0.2) price = def.basePrice
  }
  return out
}

// Box-Muller transform for standard normal from a uniform [0,1).
function normInv(u: number): number {
  // Avoid 0/1 tails.
  const x = Math.min(Math.max(u, 1e-9), 1 - 1e-9)
  // Acklam's algorithm
  const a = [-3.969683028665376e1, 2.209460984245205e2, -2.759285104469687e2, 1.38357751867269e2, -3.066479806614716e1, 2.506628277459239]
  const b = [-5.447609879822406e1, 1.615858368580409e2, -1.556989798598866e2, 6.680131188771972e1, -1.328068155288572e1]
  const c = [-7.784894002430293e-3, -3.223964580411365e-1, -2.400758277161838, -2.549732539343734, 4.374664141464968, 2.938163982698783]
  const d = [7.784695709041462e-3, 3.224671290700398e-1, 2.445134137142996, 3.754408661907416]
  const plow = 0.02425
  const phigh = 1 - plow
  let q, r
  if (x < plow) {
    q = Math.sqrt(-2 * Math.log(x))
    return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) /
      ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
  } else if (x <= phigh) {
    q = x - 0.5; r = q * q
    return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q /
      (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)
  } else {
    q = Math.sqrt(-2 * Math.log(1 - x))
    return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) /
      ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
  }
}

// Live (synthetic) quote for an instrument based on the most recent candle,
// with a fresh random-walk tick applied. This is clearly PAPER data.
export async function getQuote(symbol: string) {
  const def = INSTRUMENTS.find(d => d.symbol === symbol)
  if (!def) throw new Error('Unknown instrument: ' + symbol)
  const inst = await db.instrument.findUnique({ where: { symbol } })
  if (!inst) throw new Error('Instrument not seeded: ' + symbol)
  const last = await db.candle.findFirst({
    where: { instrumentId: inst.id, timeframe: 'M1' },
    orderBy: { ts: 'desc' },
  })
  let mid = last ? parseFloat(last.close.toString()) : def.basePrice
  // Apply a fresh tick (deterministic per minute so it's stable within a minute).
  const minute = Math.floor(Date.now() / 60000)
  const rng = mulberry32(hashSeed(symbol + ':' + minute))
  const tick = (rng() - 0.5) * 2 * def.annualVol * Math.sqrt(1 / (365 * 24 * 60)) * mid
  mid = Math.max(mid + tick, def.basePrice * 0.2)
  const pip = parseFloat(def.pipSize)
  const spread = def.spreadPips * pip
  // Round bid/ask/mid to the instrument's `precision` (decimal places), NOT
  // to pipSize, so sub-pip spreads do not collapse bid==ask after rounding.
  // pipSize is used for pip-value math; precision is used for price display.
  const priceDp = def.precision
  const bid = round(mid - spread / 2, priceDp)
  const ask = round(mid + spread / 2, priceDp)
  const ts = new Date().toISOString()
  return {
    symbol,
    bid: bid.toString(),
    ask: ask.toString(),
    mid: round(mid, priceDp).toString(),
    spread: round(spread, priceDp).toString(),
    pip: def.pipSize,
    precision: def.precision,
    ts,
    source: 'synthetic',
    isPaper: true,
  }
}

export async function listInstruments() {
  await ensureInstruments()
  const rows = await db.instrument.findMany({ orderBy: { symbol: 'asc' } })
  return rows.map(r => ({
    id: r.id, symbol: r.symbol, kind: r.kind, base: r.base, quote: r.quote,
    pipSize: r.pipSize.toString(), minSize: r.minSize.toString(), maxSize: r.maxSize.toString(),
    precision: r.precision, description: r.description,
  }))
}

// Contract size & pip value (simplified, USD account).
export function pipValuePerUnit(symbol: string, pipSize: string): Decimal {
  // For USD-quoted FX, pip value per unit = pipSize (in quote currency).
  // For JPY pairs, pipSize is 0.01 so pip value per unit = 0.01.
  // For synthetic indices we use pipSize directly.
  return D(pipSize)
}

export { round }
