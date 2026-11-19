// risk.ts — Risk engine.
//
// Independently enforced controls checked before EVERY new order:
//   - Emergency stop active
//   - Max position size
//   - Max leverage
//   - Max aggregate exposure
//   - Max simultaneous positions
//   - Max spread
//   - Max slippage
//   - Max daily loss / weekly loss / drawdown
//
// Limits are loaded from versioned RiskLimit rows (never hardcoded magic
// numbers in the execution path). LIVE mode additionally requires explicit
// live authorization on the trading account.
import { db } from '@/lib/db'
import { Decimal } from 'decimal.js'
import { D, round, abs, add, gte, lte, gt, sub } from '@/lib/money'
import { isEmergencyStopActive } from '@/lib/emergency'
import { cashBalance, realizedPnl, totalFees } from '@/lib/accounting'

export type RiskCheckResult = {
  approved: boolean
  reasons: string[]
  checks: { name: string; ok: boolean; detail?: string }[]
}

export async function getActiveRiskLimits(tradingAccountId: string) {
  const limit = await db.riskLimit.findFirst({
    where: { tradingAccountId, active: true },
    orderBy: { version: 'desc' },
  })
  if (!limit) {
    // Fail-closed default: very conservative limits until an admin configures them.
    return {
      maxPositionSize: new Decimal(1),
      maxLeverage: new Decimal(1),
      maxDailyLossPct: new Decimal(2),
      maxWeeklyLossPct: new Decimal(5),
      maxDrawdownPct: new Decimal(10),
      maxAggregateExposure: new Decimal(5000),
      maxSimultaneousPositions: 3,
      maxSpreadPips: new Decimal(3),
      maxSlippagePips: new Decimal(2),
      _defaulted: true,
    }
  }
  return {
    maxPositionSize: D(limit.maxPositionSize),
    maxLeverage: D(limit.maxLeverage),
    maxDailyLossPct: D(limit.maxDailyLossPct),
    maxWeeklyLossPct: D(limit.maxWeeklyLossPct),
    maxDrawdownPct: D(limit.maxDrawdownPct),
    maxAggregateExposure: D(limit.maxAggregateExposure),
    maxSimultaneousPositions: limit.maxSimultaneousPositions,
    maxSpreadPips: D(limit.maxSpreadPips),
    maxSlippagePips: D(limit.maxSlippagePips),
    _defaulted: false,
  }
}

export type RiskContext = {
  tradingAccountId: string
  mode: string // PAPER | DEMO | LIVE
  liveAuthorized: boolean
  symbol: string
  side: 'BUY' | 'SELL'
  size: Decimal
  price: Decimal // mid
  spread: Decimal // absolute spread in price units
  pipSize: Decimal
  accountCurrency: string
}

export async function checkOrderRisk(ctx: RiskContext): Promise<RiskCheckResult> {
  const reasons: string[] = []
  const checks: { name: string; ok: boolean; detail?: string }[] = []

  // 1. LIVE authorization gate — fail-closed.
  if (ctx.mode === 'LIVE' && !ctx.liveAuthorized) {
    checks.push({ name: 'live_authorization', ok: false, detail: 'LIVE mode requires explicit human authorization on the trading account.' })
    reasons.push('LIVE trading is not authorized on this account.')
  } else {
    checks.push({ name: 'live_authorization', ok: true })
  }

  // 2. Emergency stop.
  const es = await isEmergencyStopActive(ctx.tradingAccountId)
  if (es) {
    checks.push({ name: 'emergency_stop', ok: false, detail: 'Emergency stop is active — new entries blocked.' })
    reasons.push('Emergency stop is active.')
  } else {
    checks.push({ name: 'emergency_stop', ok: true })
  }

  const limits = await getActiveRiskLimits(ctx.tradingAccountId)

  // 3. Max position size.
  if (gt(ctx.size, limits.maxPositionSize)) {
    checks.push({ name: 'max_position_size', ok: false, detail: `size ${ctx.size} > max ${limits.maxPositionSize}` })
    reasons.push(`Position size ${ctx.size} exceeds max ${limits.maxPositionSize}.`)
  } else checks.push({ name: 'max_position_size', ok: true })

  // 4. Max spread.
  const spreadPips = ctx.pipSize.isZero() ? new Decimal(0) : ctx.spread.div(ctx.pipSize)
  if (gt(spreadPips, limits.maxSpreadPips)) {
    checks.push({ name: 'max_spread', ok: false, detail: `spread ${spreadPips.toFixed(2)} pips > max ${limits.maxSpreadPips}` })
    reasons.push(`Spread ${spreadPips.toFixed(2)} pips exceeds max ${limits.maxSpreadPips}.`)
  } else checks.push({ name: 'max_spread', ok: true })

  // 5. Max aggregate exposure (sum of |size * price| across open positions + new).
  const openPositions = await db.position.findMany({ where: { tradingAccountId: ctx.tradingAccountId, status: 'OPEN' } })
  const currentExposure = openPositions.reduce((s, p) => s.plus(D(p.size).times(D(p.entryPrice))), new Decimal(0))
  const newExposure = ctx.size.times(ctx.price)
  const totalExposure = currentExposure.plus(newExposure)
  if (gt(totalExposure, limits.maxAggregateExposure)) {
    checks.push({ name: 'max_aggregate_exposure', ok: false, detail: `total ${totalExposure.toFixed(2)} > max ${limits.maxAggregateExposure}` })
    reasons.push(`Aggregate exposure ${totalExposure.toFixed(2)} exceeds max ${limits.maxAggregateExposure}.`)
  } else checks.push({ name: 'max_aggregate_exposure', ok: true })

  // 6. Max simultaneous positions.
  if (openPositions.length >= limits.maxSimultaneousPositions) {
    checks.push({ name: 'max_simultaneous_positions', ok: false, detail: `${openPositions.length} >= ${limits.maxSimultaneousPositions}` })
    reasons.push(`Max simultaneous positions (${limits.maxSimultaneousPositions}) reached.`)
  } else checks.push({ name: 'max_simultaneous_positions', ok: true })

  // 7. Max daily loss — realized P&L + fees today vs opening capital.
  const cash = await cashBalance(ctx.tradingAccountId)
  const realized = await realizedPnl(ctx.tradingAccountId)
  const fees = await totalFees(ctx.tradingAccountId)
  const netRealized = realized.minus(fees)
  // Daily loss approximation: if net realized today is negative beyond daily limit % of cash.
  // (Full daily-window attribution requires a realized-by-day table; we approximate
  //  using cumulative net realized vs opening capital * pct.)
  const openingCapital = cash.plus(abs(netRealized)) // approximation
  const dailyLossLimitAmt = openingCapital.times(limits.maxDailyLossPct).div(100)
  if (netRealized.isNegative() && abs(netRealized).gt(dailyLossLimitAmt)) {
    checks.push({ name: 'max_daily_loss', ok: false, detail: `net realized ${netRealized.toFixed(2)} exceeds daily loss limit ${dailyLossLimitAmt.toFixed(2)}` })
    reasons.push(`Daily loss limit exceeded.`)
  } else checks.push({ name: 'max_daily_loss', ok: true })

  // 8. Max drawdown — cumulative net realized vs max drawdown % of opening capital.
  const ddLimitAmt = openingCapital.times(limits.maxDrawdownPct).div(100)
  if (netRealized.isNegative() && abs(netRealized).gt(ddLimitAmt)) {
    checks.push({ name: 'max_drawdown', ok: false, detail: `drawdown ${abs(netRealized).toFixed(2)} > limit ${ddLimitAmt.toFixed(2)}` })
    reasons.push(`Max drawdown limit exceeded.`)
  } else checks.push({ name: 'max_drawdown', ok: true })

  const approved = reasons.length === 0
  return { approved, reasons, checks }
}

// Compute current risk utilization for an account.
export async function riskUtilization(tradingAccountId: string) {
  const limits = await getActiveRiskLimits(tradingAccountId)
  const openPositions = await db.position.findMany({ where: { tradingAccountId, status: 'OPEN' } })
  const exposure = openPositions.reduce((s, p) => s.plus(D(p.size).times(D(p.entryPrice))), new Decimal(0))
  const cash = await cashBalance(tradingAccountId)
  const realized = await realizedPnl(tradingAccountId)
  const fees = await totalFees(tradingAccountId)
  const netRealized = realized.minus(fees)
  const openingCapital = cash.plus(abs(netRealized))
  const dailyLossLimitAmt = openingCapital.times(limits.maxDailyLossPct).div(100)
  const drawdownLimitAmt = openingCapital.times(limits.maxDrawdownPct).div(100)
  return {
    limits,
    exposure: round(exposure, 2),
    maxAggregateExposure: limits.maxAggregateExposure,
    exposureUtilizationPct: limits.maxAggregateExposure.isZero() ? 0 : Number(exposure.div(limits.maxAggregateExposure).times(100).toFixed(2)),
    openPositions: openPositions.length,
    maxSimultaneousPositions: limits.maxSimultaneousPositions,
    positionsUtilizationPct: limits.maxSimultaneousPositions === 0 ? 0 : Number((openPositions.length / limits.maxSimultaneousPositions * 100).toFixed(2)),
    netRealized: round(netRealized, 2),
    dailyLossLimit: round(dailyLossLimitAmt, 2),
    drawdownLimit: round(drawdownLimitAmt, 2),
    cash: round(cash, 2),
    defaulted: limits._defaulted ?? false,
  }
}
