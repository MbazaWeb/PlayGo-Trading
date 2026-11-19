import { NextRequest } from 'next/server'
import { db } from '@/lib/db'
import { json, err, requireUser } from '@/lib/api'
import { runBacktest, BacktestParams } from '@/lib/backtest'
import { audit } from '@/lib/audit'

export async function POST(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const user = await requireUser()
  if (!user) return err('Unauthorized', 401)
  const { id } = await params
  const strat = await db.strategy.findUnique({ where: { id } })
  if (!strat) return err('Strategy not found', 404)
  const body = await req.json().catch(() => ({})) as {
    instrument?: string; timeframe?: string; days?: number;
    params?: Partial<BacktestParams>;
  }
  const instrument = body.instrument || 'EUR/USD'
  const timeframe = body.timeframe || 'M15'
  const days = body.days || 60
  const to = new Date()
  const from = new Date(to.getTime() - days * 24 * 60 * 60 * 1000)
  const btParams: BacktestParams = {
    fastPeriod: body.params?.fastPeriod ?? 10,
    slowPeriod: body.params?.slowPeriod ?? 30,
    stopLossPips: body.params?.stopLossPips ?? 20,
    takeProfitPips: body.params?.takeProfitPips ?? 40,
    size: body.params?.size ?? 1,
  }
  try {
    const result = await runBacktest({ strategyId: strat.id, instrument, timeframe, fromDate: from, toDate: to, params: btParams })
    await audit({ userId: user.id, action: 'BACKTEST_RUN', entity: 'Strategy', entityId: strat.id, after: { instrument, timeframe, trades: result.trades, netReturn: result.netReturn } })
    return json({ result })
  } catch (e) {
    return err((e as Error).message, 400)
  }
}
