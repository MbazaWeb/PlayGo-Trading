import { NextRequest } from 'next/server'
import { db } from '@/lib/db'
import { json, err, requireUser } from '@/lib/api'

export async function GET(req: NextRequest) {
  const user = await requireUser()
  if (!user) return err('Unauthorized', 401)
  const { searchParams } = new URL(req.url)
  const orderId = searchParams.get('orderId')
  const accountId = searchParams.get('accountId')
  if (!accountId) return err('accountId required')
  const acc = await db.tradingAccount.findFirst({ where: { id: accountId, userId: user.id } })
  if (!acc) return err('Account not found', 404)
  let where = {}
  if (orderId) {
    where = { orderId }
  } else {
    where = { order: { tradingAccountId: acc.id } }
  }
  const events = await db.tradeEvent.findMany({ where, orderBy: { createdAt: 'asc' }, take: 500, include: { order: true } })
  return json({ events })
}
