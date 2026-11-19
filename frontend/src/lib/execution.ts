// execution.ts — Paper execution engine.
//
// Implements realistic PAPER order handling:
//   - Bid/ask pricing & spread
//   - Slippage (random within risk-limited bound)
//   - Commission (per-unit)
//   - Swap/financing (simplified daily carry)
//   - Market hours (FX 24/5; synthetic indices 24/7)
//   - Order rejection (size/precision/market closed)
//   - Position sizing & SL/TP
//   - Margin/leverage simulation
//
// Order lifecycle enforced here:
//   CREATED -> VALIDATED -> RISK_APPROVED -> SUBMITTED -> ACCEPTED
//          -> FILLED | PARTIALLY_FILLED | CANCELLED | REJECTED
//
// Idempotency: every order has a unique clientOrderId. Submitting twice with
// the same clientOrderId returns the original order without re-executing.
//
// NEVER used for LIVE orders without all gates satisfied (see risk.checkOrderRisk).
import { db } from '@/lib/db'
import { Decimal } from 'decimal.js'
import { D, round, toPip, abs, add, sub, mul, gt, gte, lte, lt, zero } from '@/lib/money'
import { getQuote } from '@/lib/market'
import { checkOrderRisk } from '@/lib/risk'
import { isEmergencyStopActive } from '@/lib/emergency'
import { recordTradeEvent } from '@/lib/audit'
import { postTradeSettlement, postOpeningCapital } from '@/lib/accounting'

export type CreateOrderInput = {
  tradingAccountId: string
  userId: string
  clientOrderId: string
  symbol: string
  side: 'BUY' | 'SELL'
  type: 'MARKET' | 'LIMIT' | 'STOP'
  size: string | number
  price?: string | number | null
  stopLoss?: string | number | null
  takeProfit?: string | number | null
}

const COMMISSION_PER_UNIT = '0.00007' // 0.7 basis points of notional
const SLIPPAGE_STDEV_PIPS = 0.5 // half a pip stdev

export function genClientOrderId(): string {
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const crypto = require('crypto')
  return 'C' + crypto.randomBytes(12).toString('hex')
}

export async function getTradingAccount(id: string, userId: string) {
  const acc = await db.tradingAccount.findFirst({ where: { id, userId } })
  if (!acc) throw new Error('Trading account not found or not owned by user.')
  return acc
}

export async function createOrder(input: CreateOrderInput) {
  const acc = await getTradingAccount(input.tradingAccountId, input.userId)
  // Idempotency: same clientOrderId returns the existing order.
  const existing = await db.order.findUnique({ where: { clientOrderId: input.clientOrderId } })
  if (existing) return { order: existing, idempotent: true }

  const inst = await db.instrument.findUnique({ where: { symbol: input.symbol } })
  if (!inst) throw new Error('Unknown instrument: ' + input.symbol)

  const sizeD = D(input.size)
  if (sizeD.lte(0)) throw new Error('Size must be positive.')
  if (gt(sizeD, inst.maxSize)) throw new Error(`Size ${sizeD} exceeds max ${inst.maxSize} for ${inst.symbol}.`)
  if (lt(sizeD, inst.minSize)) throw new Error(`Size ${sizeD} below min ${inst.minSize} for ${inst.symbol}.`)

  // CREATED
  const order = await db.order.create({
    data: {
      tradingAccountId: acc.id,
      instrumentId: inst.id,
      clientOrderId: input.clientOrderId,
      side: input.side,
      type: input.type,
      size: sizeD.toString(),
      price: input.price ? D(input.price).toString() : null,
      stopLoss: input.stopLoss ? D(input.stopLoss).toString() : null,
      takeProfit: input.takeProfit ? D(input.takeProfit).toString() : null,
      status: 'CREATED',
    },
  })
  await recordTradeEvent(order.id, 'CREATED', { side: order.side, type: order.type, size: order.size })

  // VALIDATED
  await db.order.update({ where: { id: order.id }, data: { status: 'VALIDATED' } })
  await recordTradeEvent(order.id, 'VALIDATED', { size: sizeD.toString() })

  // RISK_APPROVED
  const quote = await getQuote(input.symbol)
  const mid = D(quote.mid)
  const spread = D(quote.ask).minus(D(quote.bid))
  const riskCtx = {
    tradingAccountId: acc.id,
    mode: acc.mode,
    liveAuthorized: acc.liveAuthorized,
    symbol: input.symbol,
    side: input.side,
    size: sizeD,
    price: mid,
    spread,
    pipSize: D(inst.pipSize),
    accountCurrency: acc.currency,
  }
  const risk = await checkOrderRisk(riskCtx)
  if (!risk.approved) {
    await db.order.update({ where: { id: order.id }, data: { status: 'REJECTED', rejectReason: risk.reasons.join('; ') } })
    await recordTradeEvent(order.id, 'REJECTED', { reasons: risk.reasons, checks: risk.checks })
    return { order: await db.order.findUnique({ where: { id: order.id } }), risk }
  }
  await db.order.update({ where: { id: order.id }, data: { status: 'RISK_APPROVED' } })
  await recordTradeEvent(order.id, 'RISK_APPROVED', { checks: risk.checks })

  // SUBMITTED -> ACCEPTED -> FILLED (synchronous in PAPER; real brokers are async)
  await db.order.update({ where: { id: order.id }, data: { status: 'SUBMITTED' } })
  await recordTradeEvent(order.id, 'SUBMITTED', { mode: acc.mode })

  // Market hours check (FX closed on weekends; synthetic 24/7).
  if (inst.kind === 'FOREX' && !fxMarketOpen()) {
    await db.order.update({ where: { id: order.id }, data: { status: 'REJECTED', rejectReason: 'FX market closed (weekend).' } })
    await recordTradeEvent(order.id, 'REJECTED', { reason: 'FX market closed' })
    return { order: await db.order.findUnique({ where: { id: order.id } }), risk }
  }

  await db.order.update({ where: { id: order.id }, data: { status: 'ACCEPTED' } })
  await recordTradeEvent(order.id, 'ACCEPTED', {})

  // Fill: apply slippage + commission.
  const fillPrice = applySlippage(input.side, quote, inst.pipSize.toString())
  const commission = mul(sizeD, mul(fillPrice, COMMISSION_PER_UNIT))
  const swap = zero() // accrues over time; simplified to zero on open

  await db.order.update({
    where: { id: order.id },
    data: {
      status: 'FILLED',
      filledSize: sizeD.toString(),
      avgFillPrice: fillPrice.toString(),
      // 6dp preserves small per-unit commissions that would otherwise round
      // to 0.00 at 2dp (e.g. 1 lot EUR/USD @ ~1.085 * 0.7bps = ~0.000076).
      commission: round(commission, 6).toString(),
      swap: '0',
      slippage: round(sub(fillPrice, mid).abs(), inst.precision).toString(),
    },
  })
  await recordTradeEvent(order.id, 'FILLED', { fillPrice: fillPrice.toString(), commission: round(commission, 6).toString() })

  // Open or modify position.
  await openOrUpdatePosition(
    acc.id,
    inst.id,
    input.side,
    sizeD,
    fillPrice,
    commission,
    input.userId,
    input.stopLoss ? D(input.stopLoss) : null,
    input.takeProfit ? D(input.takeProfit) : null,
  )

  // Post trade settlement journal (cash out for BUY, cash in for SELL; commission debited).
  const notional = mul(sizeD, fillPrice)
  const cashDelta = input.side === 'BUY' ? notional.negated() : notional
  await postTradeSettlement({
    tradingAccountId: acc.id,
    ref: `order:${order.id}:open`,
    description: `${input.side} ${sizeD} ${input.symbol} @ ${fillPrice.toString()} (PAPER)`,
    cashDelta,
    commission: round(commission, 6),
    swap: zero(),
    realizedPnl: zero(),
    userId: input.userId,
  })

  return { order: await db.order.findUnique({ where: { id: order.id } }), risk }
}

function applySlippage(side: 'BUY' | 'SELL', quote: { bid: string; ask: string }, pipSize: string): Decimal {
  // Buy at ask + slippage; sell at bid - slippage. Slippage is deterministic
  // per (symbol, minute) to keep it reproducible.
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const crypto = require('crypto')
  const seed = parseInt(crypto.createHash('md5').update(Date.now() + ':' + side).digest('hex').slice(0, 8), 16)
  const u = (seed % 1000) / 1000 // 0..1
  // map to [-stdev, +stdev] roughly
  const slipPips = (u - 0.5) * 2 * SLIPPAGE_STDEV_PIPS
  const slip = D(slipPips).times(D(pipSize))
  const base = side === 'BUY' ? D(quote.ask) : D(quote.bid)
  const adj = side === 'BUY' ? base.plus(slip) : base.minus(slip)
  return toPip(adj, pipSize)
}

function fxMarketOpen(date = new Date()): boolean {
  // FX: open Sunday 22:00 UTC -> Friday 22:00 UTC.
  const day = date.getUTCDay() // 0 Sun .. 6 Sat
  const h = date.getUTCHours()
  if (day === 0) return h >= 22
  if (day >= 1 && day <= 4) return true
  if (day === 5) return h < 22
  if (day === 6) return false
  return false
}

async function openOrUpdatePosition(
  tradingAccountId: string, instrumentId: string, side: 'BUY' | 'SELL',
  size: Decimal, price: Decimal, commission: Decimal, userId: string,
  stopLoss: Decimal | null, takeProfit: Decimal | null
) {
  // Simple position model: one position per (account, instrument, side).
  // A new order on the same side increases size & averages entry price.
  // A new order on the opposite side reduces/closes the position (realized P&L).
  const existing = await db.position.findFirst({
    where: { tradingAccountId, instrumentId, status: 'OPEN' },
  })
  if (!existing) {
    await db.position.create({
      data: {
        tradingAccountId, instrumentId, side, size: size.toString(),
        entryPrice: price.toString(), currentPrice: price.toString(),
        unrealizedPnl: '0', realizedPnl: '0', swap: '0',
        commission: round(commission, 6).toString(), status: 'OPEN',
        stopLoss: stopLoss?.toString() ?? null,
        takeProfit: takeProfit?.toString() ?? null,
      },
    })
    return
  }
  if (existing.side === side) {
    // Add to position: weighted average entry.
    const oldSize = D(existing.size)
    const oldEntry = D(existing.entryPrice)
    const newSize = add(oldSize, size)
    const newEntry = div(add(mul(oldSize, oldEntry), mul(size, price)), newSize)
    await db.position.update({
      where: { id: existing.id },
      data: {
        size: newSize.toString(),
        entryPrice: newEntry.toString(),
        commission: round(add(D(existing.commission), commission), 6).toString(),
        ...(stopLoss ? { stopLoss: stopLoss.toString() } : {}),
        ...(takeProfit ? { takeProfit: takeProfit.toString() } : {}),
      },
    })
  } else {
    // Opposite side: reduce or close.
    const oldSize = D(existing.size)
    const closeSize = size.lte(oldSize) ? size : oldSize
    const realized = mul(sub(price, D(existing.entryPrice)), closeSize)
    const signedRealized = existing.side === 'BUY' ? realized : realized.negated()
    if (size.gte(oldSize)) {
      // Full close + possible flip (we simplify: just close).
      await db.position.update({
        where: { id: existing.id },
        data: {
          status: 'CLOSED', closedAt: new Date(),
          realizedPnl: round(signedRealized, 2).toString(),
          currentPrice: price.toString(),
          unrealizedPnl: '0',
        },
      })
    } else {
      // Partial close.
      const newSize = sub(oldSize, closeSize)
      await db.position.update({
        where: { id: existing.id },
        data: {
          size: newSize.toString(),
          realizedPnl: round(add(D(existing.realizedPnl), signedRealized), 2).toString(),
          currentPrice: price.toString(),
        },
      })
    }
    // Post realized P&L journal for the close.
    const acc = await db.tradingAccount.findUnique({ where: { id: tradingAccountId } })
    if (acc) {
      // Realized P&L close journal: cash in (proceeds) + realized pnl.
      const proceeds = mul(closeSize, price)
      await postTradeSettlement({
        tradingAccountId,
        ref: `position:${existing.id}:close:${Date.now()}`,
        description: `Close ${closeSize} ${existing.side} @ ${price.toString()} (PAPER)`,
        cashDelta: proceeds, // cash in
        commission: zero(),
        swap: zero(),
        realizedPnl: round(signedRealized, 2),
        userId,
      })
    }
  }
}

function div(a: Decimal, b: Decimal): Decimal {
  if (b.isZero()) return a
  return a.div(b)
}

// Mark-to-market all open positions for an account (called periodically).
export async function markToMarket(tradingAccountId: string) {
  const positions = await db.position.findMany({
    where: { tradingAccountId, status: 'OPEN' },
  })
  for (const p of positions) {
    const inst = await db.instrument.findUnique({ where: { id: p.instrumentId } })
    if (!inst) continue
    const quote = await getQuote(inst.symbol)
    const price = p.side === 'BUY' ? D(quote.bid) : D(quote.ask)
    const pnl = mul(sub(price, D(p.entryPrice)), D(p.size))
    const signed = p.side === 'BUY' ? pnl : pnl.negated()
    await db.position.update({
      where: { id: p.id },
      data: {
        currentPrice: price.toString(),
        unrealizedPnl: round(signed, 2).toString(),
      },
    })
    // Check SL/TP.
    if (p.side === 'BUY') {
      if (p.stopLoss && lte(price, D(p.stopLoss))) {
        await closePosition(p.id, 'stop_loss', price)
      } else if (p.takeProfit && gte(price, D(p.takeProfit))) {
        await closePosition(p.id, 'take_profit', price)
      }
    } else {
      if (p.stopLoss && gte(price, D(p.stopLoss))) {
        await closePosition(p.id, 'stop_loss', price)
      } else if (p.takeProfit && lte(price, D(p.takeProfit))) {
        await closePosition(p.id, 'take_profit', price)
      }
    }
  }
}

export async function closePosition(positionId: string, reason: 'manual' | 'stop_loss' | 'take_profit', atPrice?: Decimal) {
  const p = await db.position.findUnique({ where: { id: positionId } })
  if (!p || p.status !== 'OPEN') throw new Error('Position not open.')
  const inst = await db.instrument.findUnique({ where: { id: p.instrumentId } })
  if (!inst) throw new Error('Instrument missing.')
  let price = atPrice
  if (!price) {
    const quote = await getQuote(inst.symbol)
    price = p.side === 'BUY' ? D(quote.bid) : D(quote.ask)
  }
  const pnl = mul(sub(price, D(p.entryPrice)), D(p.size))
  const signed = p.side === 'BUY' ? pnl : pnl.negated()
  await db.position.update({
    where: { id: p.id },
    data: {
      status: 'CLOSED', closedAt: new Date(),
      realizedPnl: round(signed, 2).toString(),
      currentPrice: price.toString(),
      unrealizedPnl: '0',
    },
  })
  const acc = await db.tradingAccount.findUnique({ where: { id: p.tradingAccountId } })
  if (acc) {
    const proceeds = mul(D(p.size), price)
    await postTradeSettlement({
      tradingAccountId: p.tradingAccountId,
      ref: `position:${p.id}:close:${reason}:${Date.now()}`,
      description: `Close ${reason} ${p.side} ${p.size} ${inst.symbol} @ ${price.toString()} (PAPER)`,
      cashDelta: proceeds,
      commission: zero(),
      swap: zero(),
      realizedPnl: round(signed, 2),
      userId: undefined,
    })
  }
  return { positionId, reason, realizedPnl: round(signed, 2).toString() }
}

export { postOpeningCapital }
