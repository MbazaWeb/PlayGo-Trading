import { NextRequest } from 'next/server'
import { db } from '@/lib/db'
import { json, err, requireUser } from '@/lib/api'

export async function GET(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const user = await requireUser()
  if (!user) return err('Unauthorized', 401)
  const { id } = await params
  const order = await db.order.findUnique({
    where: { id },
    include: { instrument: true, events: { orderBy: { createdAt: 'asc' } } },
  })
  if (!order) return err('Order not found', 404)
  const acc = await db.tradingAccount.findUnique({ where: { id: order.tradingAccountId } })
  if (!acc || acc.userId !== user.id) return err('Forbidden', 403)
  return json({ order, events: order.events })
}
