import { NextRequest } from 'next/server'
import { db } from '@/lib/db'
import { json, err, requireUser } from '@/lib/api'
import { markToMarket } from '@/lib/execution'
import { cashBalance, realizedPnl, totalFees } from '@/lib/accounting'
import { riskUtilization } from '@/lib/risk'
import { getEmergencyStopState } from '@/lib/emergency'
import { D } from '@/lib/money'

export async function GET(req: NextRequest) {
  const user = await requireUser()
  if (!user) return err('Unauthorized', 401)
  const { searchParams } = new URL(req.url)
  const accountId = searchParams.get('accountId')
  if (!accountId) return err('accountId required')
  const acc = await db.tradingAccount.findFirst({ where: { id: accountId, userId: user.id } })
  if (!acc) return err('Account not found', 404)
  await markToMarket(acc.id)
  const cash = await cashBalance(acc.id)
  const realized = await realizedPnl(acc.id)
  const fees = await totalFees(acc.id)
  const positions = await db.position.findMany({ where: { tradingAccountId: acc.id, status: 'OPEN' }, include: { instrument: true } })
  let unrealized = D(0)
  for (const p of positions) unrealized = unrealized.plus(D(p.unrealizedPnl))
  const equity = cash.plus(realized).minus(fees).plus(unrealized)
  const util = await riskUtilization(acc.id)
  const es = await getEmergencyStopState(acc.id)
  const orders = await db.order.findMany({ where: { tradingAccountId: acc.id }, orderBy: { createdAt: 'desc' }, take: 10, include: { instrument: true } })
  const closedPositions = await db.position.findMany({ where: { tradingAccountId: acc.id, status: 'CLOSED' }, orderBy: { closedAt: 'desc' }, take: 50, include: { instrument: true } })
  return json({
    account: { id: acc.id, label: acc.label, mode: acc.mode, broker: acc.broker, currency: acc.currency, liveAuthorized: acc.liveAuthorized },
    balance: cash.toString(),
    realizedPnl: realized.toString(),
    fees: fees.toString(),
    unrealizedPnl: unrealized.toString(),
    equity: equity.toString(),
    openPositions: positions,
    closedPositions,
    recentOrders: orders,
    risk: util,
    emergencyStop: es,
  })
}
