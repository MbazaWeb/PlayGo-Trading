import { NextRequest } from 'next/server'
import { db } from '@/lib/db'
import { json, err, requireUser } from '@/lib/api'
import { audit } from '@/lib/audit'

export async function POST(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const user = await requireUser()
  if (!user) return err('Unauthorized', 401)
  const { id } = await params
  const strat = await db.strategy.findUnique({ where: { id } })
  if (!strat) return err('Strategy not found', 404)
  const updated = await db.strategy.update({ where: { id }, data: { status: 'APPROVED' } })
  await audit({ userId: user.id, action: 'STRATEGY_APPROVE', entity: 'Strategy', entityId: id, before: { status: strat.status }, after: { status: 'APPROVED' } })
  return json({ strategy: updated })
}
