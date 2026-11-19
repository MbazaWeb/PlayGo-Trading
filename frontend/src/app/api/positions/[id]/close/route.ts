import { NextRequest } from 'next/server'
import { db } from '@/lib/db'
import { json, err, requireUser } from '@/lib/api'
import { closePosition } from '@/lib/execution'
import { audit } from '@/lib/audit'

export async function POST(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const user = await requireUser()
  if (!user) return err('Unauthorized', 401)
  const { id } = await params
  const pos = await db.position.findUnique({ where: { id }, include: { instrument: true } })
  if (!pos) return err('Position not found', 404)
  const acc = await db.tradingAccount.findUnique({ where: { id: pos.tradingAccountId } })
  if (!acc || acc.userId !== user.id) return err('Forbidden', 403)
  try {
    const result = await closePosition(id, 'manual')
    await audit({ userId: user.id, action: 'POSITION_CLOSE', entity: 'Position', entityId: id, after: result })
    return json(result)
  } catch (e) {
    return err((e as Error).message, 400)
  }
}
