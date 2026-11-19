import { NextRequest } from 'next/server'
import { db } from '@/lib/db'
import { json, err, requireAdmin } from '@/lib/api'

export async function GET(req: NextRequest) {
  const user = await requireAdmin()
  if (!user) return err('Unauthorized', 401)
  const users = await db.user.findMany({ select: { id: true, email: true, name: true, role: true, createdAt: true }, orderBy: { createdAt: 'desc' } })
  const accounts = await db.tradingAccount.findMany({ include: { user: { select: { email: true } } } })
  const health = await db.systemHealth.findMany({ orderBy: { checkedAt: 'desc' }, take: 50 })
  return json({ users, accounts, health })
}
