import { NextRequest } from 'next/server'
import { db } from '@/lib/db'
import { json, err, requireUser } from '@/lib/api'
import { markToMarket } from '@/lib/execution'

export async function GET(req: NextRequest) {
  const user = await requireUser()
  if (!user) return err('Unauthorized', 401)
  const { searchParams } = new URL(req.url)
  const accountId = searchParams.get('accountId')
  if (!accountId) return err('accountId required')
  const acc = await db.tradingAccount.findFirst({ where: { id: accountId, userId: user.id } })
  if (!acc) return err('Account not found', 404)
  await markToMarket(acc.id)
  const positions = await db.position.findMany({
    where: { tradingAccountId: acc.id },
    orderBy: { openedAt: 'desc' },
    include: { instrument: true },
    take: 100,
  })
  return json({ positions })
}
