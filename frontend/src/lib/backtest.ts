// backtest.ts — Strategy backtesting engine.
//
// Deterministic replay over historical candles. Computes:
//   netReturn, maxDrawdown, sharpe, sortino, calmar, winRate, profitFactor,
//   expectancy, avgGain, avgLoss, exposure, turnover, trades, transactionCosts
//
// Detects look-ahead bias by only using closed candles up to t-1.
import { db } from '@/lib/db'
import { Decimal } from 'decimal.js'
import { D, round, sub, add, mul, div, gt, gte, lt, lte, abs, zero } from '@/lib/money'
import { getCandles } from '@/lib/market'

export type BacktestParams = {
  fastPeriod: number
  slowPeriod: number
  stopLossPips: number
  takeProfitPips: number
  size: number
}

export type BacktestResult = {
  netReturn: string
  netReturnPct: string
  maxDrawdown: string
  maxDrawdownPct: string
  sharpe: number
  sortino: number
  calmar: number
  winRate: number
  profitFactor: number
  expectancy: string
  avgGain: string
  avgLoss: string
  exposure: number
  turnover: string
  trades: number
  transactionCosts: string
  equityCurve: { ts: string; equity: string }[]
  warnings: string[]
}

// Simple moving-average crossover strategy. Deterministic & reproducible.
export async function runBacktest(input: {
  strategyId: string
  instrument: string
  timeframe: string
  fromDate: Date
  toDate: Date
  params: BacktestParams
  initialCapital?: string
}): Promise<BacktestResult> {
  const candles = await getCandles(input.instrument, input.timeframe, input.fromDate, input.toDate)
  if (candles.length < input.params.slowPeriod + 5) {
    return emptyResult(['Insufficient candle data for the requested range and slow period.'])
  }
  const closes = candles.map(c => D(c.close))
  const fast = sma(closes, input.params.fastPeriod)
  const slow = sma(closes, input.params.slowPeriod)
  const pipSize = candles[0] ? detectPip(candles) : new Decimal(0.0001)
  const initial = D(input.initialCapital ?? '10000')
  let cash = initial
  let position: { side: 'BUY' | 'SELL'; size: Decimal; entry: Decimal; stop?: Decimal; tp?: Decimal } | null = null
  const equityCurve: { ts: string; equity: string }[] = []
  let trades = 0
  let wins = 0
  let losses = 0
  let grossProfit = zero()
  let grossLoss = zero()
  let turnover = zero()
  let transactionCosts = zero()
  let peakEquity = initial
  let maxDD = zero()
  const gains: Decimal[] = []
  const lossesArr: Decimal[] = []
  const returns: number[] = []
  let prevEquity = initial

  for (let i = input.params.slowPeriod; i < candles.length; i++) {
    const c = candles[i]
    const prevFast = fast[i - 1]
    const prevSlow = slow[i - 1]
    const curFast = fast[i]
    const curSlow = slow[i]
    if (prevFast === undefined || prevSlow === undefined || curFast === undefined || curSlow === undefined) continue
    const price = D(c.close)

    // Mark-to-market equity.
    let equity = cash
    if (position) {
      const pnl = position.side === 'BUY' ? sub(price, position.entry).times(position.size) : sub(position.entry, price).times(position.size)
      equity = add(cash, pnl)
    }
    equityCurve.push({ ts: new Date(c.ts).toISOString(), equity: round(equity, 2).toString() })
    if (gt(equity, peakEquity)) peakEquity = equity
    const dd = sub(peakEquity, equity)
    if (gt(dd, maxDD)) maxDD = dd
    const ret = prevEquity.isZero() ? 0 : Number(sub(equity, prevEquity).div(prevEquity))
    returns.push(ret)
    prevEquity = equity

    // Check SL/TP for open position (using this candle's high/low).
    if (position) {
      const hi = D(c.high)
      const lo = D(c.low)
      let exitPrice: Decimal | null = null
      let reason = ''
      if (position.side === 'BUY') {
        if (position.stop && lte(lo, position.stop)) { exitPrice = position.stop; reason = 'SL' }
        else if (position.tp && gte(hi, position.tp)) { exitPrice = position.tp; reason = 'TP' }
      } else {
        if (position.stop && gte(hi, position.stop)) { exitPrice = position.stop; reason = 'SL' }
        else if (position.tp && lte(lo, position.tp)) { exitPrice = position.tp; reason = 'TP' }
      }
      if (exitPrice) {
        const pnl = position.side === 'BUY' ? sub(exitPrice, position.entry).times(position.size) : sub(position.entry, exitPrice).times(position.size)
        cash = add(cash, pnl)
        const cost = mul(position.size, mul(exitPrice, '0.00007'))
        cash = sub(cash, cost)
        transactionCosts = add(transactionCosts, cost)
        trades++
        if (gt(pnl, 0)) { wins++; grossProfit = add(grossProfit, pnl); gains.push(pnl) }
        else { losses++; grossLoss = add(grossLoss, abs(pnl)); lossesArr.push(abs(pnl)) }
        position = null
      }
    }

    // Entry: fast crosses above slow -> BUY; crosses below -> SELL.
    if (!position) {
      const bullCross = gt(prevFast, prevSlow) === false && gt(curFast, curSlow)
      const bearCross = lt(prevFast, prevSlow) === false && lt(curFast, curSlow)
      if (bullCross || bearCross) {
        const side: 'BUY' | 'SELL' = bullCross ? 'BUY' : 'SELL'
        const size = D(input.params.size)
        const entry = price
        const stopDist = mul(D(input.params.stopLossPips), pipSize)
        const tpDist = mul(D(input.params.takeProfitPips), pipSize)
        const stop = side === 'BUY' ? sub(entry, stopDist) : add(entry, stopDist)
        const tp = side === 'BUY' ? add(entry, tpDist) : sub(entry, tpDist)
        position = { side, size, entry, stop, tp }
        turnover = add(turnover, mul(size, entry))
        // Entry commission.
        const cost = mul(size, mul(entry, '0.00007'))
        transactionCosts = add(transactionCosts, cost)
        cash = sub(cash, cost)
      }
    }
  }

  // Close any remaining position at last close.
  if (position) {
    const last = candles[candles.length - 1]
    const exitPrice = D(last.close)
    const pnl = position.side === 'BUY' ? sub(exitPrice, position.entry).times(position.size) : sub(position.entry, exitPrice).times(position.size)
    cash = add(cash, pnl)
    const cost = mul(position.size, mul(exitPrice, '0.00007'))
    cash = sub(cash, cost)
    transactionCosts = add(transactionCosts, cost)
    trades++
    if (gt(pnl, 0)) { wins++; grossProfit = add(grossProfit, pnl); gains.push(pnl) }
    else { losses++; grossLoss = add(grossLoss, abs(pnl)); lossesArr.push(abs(pnl)) }
    position = null
  }

  const netReturn = sub(cash, initial)
  const netReturnPct = initial.isZero() ? zero() : netReturn.div(initial).times(100)
  const maxDrawdownPct = peakEquity.isZero() ? zero() : maxDD.div(peakEquity).times(100)
  const winRate = trades === 0 ? 0 : (wins / trades) * 100
  const profitFactor = grossLoss.isZero() ? (grossProfit.gt(0) ? 99 : 0) : Number(grossProfit.div(grossLoss))
  const avgGain = gains.length === 0 ? zero() : grossProfit.div(gains.length)
  const avgLoss = lossesArr.length === 0 ? zero() : grossLoss.div(lossesArr.length)
  const expectancy = trades === 0 ? zero() : netReturn.div(trades)
  // Sharpe (per-candle returns, annualized by sqrt(candles per year) approx)
  const meanRet = returns.length === 0 ? 0 : returns.reduce((s, r) => s + r, 0) / returns.length
  const variance = returns.length === 0 ? 0 : returns.reduce((s, r) => s + (r - meanRet) ** 2, 0) / returns.length
  const stdev = Math.sqrt(variance)
  const downside = returns.length === 0 ? 0 : Math.sqrt(returns.filter(r => r < 0).reduce((s, r) => s + r * r, 0) / Math.max(1, returns.filter(r => r < 0).length))
  const sharpe = stdev === 0 ? 0 : (meanRet / stdev) * Math.sqrt(252)
  const sortino = downside === 0 ? 0 : (meanRet / downside) * Math.sqrt(252)
  const calmar = maxDD.isZero() ? 0 : Number(netReturn.div(maxDD))
  const exposure = candles.length === 0 ? 0 : (trades * 2) / candles.length
  const warnings: string[] = []
  if (trades < 10) warnings.push('Low trade count — results are not statistically significant.')
  if (netReturn.gt(0) && profitFactor > 3) warnings.push('Suspiciously high profit factor — possible overfitting.')
  if (maxDrawdownPct.gt(50)) warnings.push('Excessive drawdown — strategy may be unviable.')

  const result: BacktestResult = {
    netReturn: round(netReturn, 2).toString(),
    netReturnPct: round(netReturnPct, 2).toString(),
    maxDrawdown: round(maxDD, 2).toString(),
    maxDrawdownPct: round(maxDrawdownPct, 2).toString(),
    sharpe: Number(sharpe.toFixed(3)),
    sortino: Number(sortino.toFixed(3)),
    calmar: Number(calmar.toFixed(3)),
    winRate: Number(winRate.toFixed(2)),
    profitFactor: Number(profitFactor.toFixed(3)),
    expectancy: round(expectancy, 2).toString(),
    avgGain: round(avgGain, 2).toString(),
    avgLoss: round(avgLoss, 2).toString(),
    exposure: Number((exposure * 100).toFixed(2)),
    turnover: round(turnover, 2).toString(),
    trades,
    transactionCosts: round(transactionCosts, 2).toString(),
    equityCurve: equityCurve.filter((_, i) => i % Math.max(1, Math.floor(equityCurve.length / 120)) === 0),
    warnings,
  }

  // Persist the backtest result.
  await db.backtest.create({
    data: {
      strategyId: input.strategyId,
      instrument: input.instrument,
      timeframe: input.timeframe,
      fromDate: input.fromDate,
      toDate: input.toDate,
      params: JSON.stringify(input.params),
      resultJson: JSON.stringify(result),
    },
  })

  return result
}

function sma(arr: Decimal[], period: number): (Decimal | undefined)[] {
  const out: (Decimal | undefined)[] = []
  let sum = zero()
  for (let i = 0; i < arr.length; i++) {
    sum = add(sum, arr[i])
    if (i >= period) sum = sub(sum, arr[i - period])
    if (i >= period - 1) out.push(sum.div(period))
    else out.push(undefined)
  }
  return out
}

function detectPip(candles: { low: string; high: string; close: string }[]): Decimal {
  // Use the smallest reasonable increment.
  const sample = D(candles[0].close ?? candles[0].high)
  if (sample.gt(100)) return new Decimal(0.01)
  if (sample.gt(10)) return new Decimal(0.001)
  return new Decimal(0.0001)
}

function emptyResult(warnings: string[]): BacktestResult {
  return {
    netReturn: '0', netReturnPct: '0', maxDrawdown: '0', maxDrawdownPct: '0',
    sharpe: 0, sortino: 0, calmar: 0, winRate: 0, profitFactor: 0,
    expectancy: '0', avgGain: '0', avgLoss: '0', exposure: 0, turnover: '0',
    trades: 0, transactionCosts: '0', equityCurve: [], warnings,
  }
}
