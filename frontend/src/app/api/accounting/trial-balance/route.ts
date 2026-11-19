import { NextRequest } from 'next/server'
import { json, err, requireUser } from '@/lib/api'
import { trialBalance, cashBalance, realizedPnl, totalFees } from '@/lib/accounting'
import { db } from '@/lib/db'

export async function GET(req: NextRequest) {
  const user = await requireUser()
  if (!user) return err('Unauthorized', 401)
  const { searchParams } = new URL(req.url)
  const accountId = searchParams.get('accountId')
  if (!accountId) return err('accountId required')
  const acc = await db.tradingAccount.findFirst({ where: { id: accountId, userId: user.id } })
  if (!acc) return err('Account not found', 404)
  const tb = await trialBalance(acc.id)
  const cash = await cashBalance(acc.id)
  const realized = await realizedPnl(acc.id)
  const fees = await totalFees(acc.id)
  const positions = await db.position.findMany({ where: { tradingAccountId: acc.id, status: 'OPEN' }, include: { instrument: true } })
  let unrealized = 0
  for (const p of positions) {
    unrealized += Number(p.unrealizedPnl.toString())
  }
  return json({
    trialBalance: { debit: tb.debit.toString(), credit: tb.credit.toString(), balanced: tb.balanced },
    cash: cash.toString(),
    realizedPnl: realized.toString(),
    fees: fees.toString(),
    unrealizedPnl: unrealized.toFixed(2),
    equity: cash.plus(realized).minus(fees).plus(unrealized).toFixed(2),
    openPositions: positions.length,
  })
}
