import { NextRequest } from 'next/server'
import { db } from '@/lib/db'
import { json, err, requireUser } from '@/lib/api'
import { audit } from '@/lib/audit'

export async function GET(req: NextRequest) {
  const user = await requireUser()
  if (!user) return err('Unauthorized', 401)
  const { searchParams } = new URL(req.url)
  const accountId = searchParams.get('accountId')
  if (!accountId) return err('accountId required')
  const acc = await db.tradingAccount.findFirst({ where: { id: accountId, userId: user.id } })
  if (!acc) return err('Account not found', 404)
  const limit = await db.riskLimit.findFirst({ where: { tradingAccountId: acc.id, active: true }, orderBy: { version: 'desc' } })
  return json({ limit })
}

export async function PUT(req: NextRequest) {
  const user = await requireUser()
  if (!user) return err('Unauthorized', 401)
  const body = await req.json().catch(() => ({}))
  const accountId = body.accountId
  if (!accountId) return err('accountId required')
  const acc = await db.tradingAccount.findFirst({ where: { id: accountId, userId: user.id } })
  if (!acc) return err('Account not found', 404)
  const prev = await db.riskLimit.findFirst({ where: { tradingAccountId: acc.id, active: true }, orderBy: { version: 'desc' } })
  const nextVersion = (prev?.version ?? 0) + 1
  // Retire previous active limits (versioned configuration).
  await db.riskLimit.updateMany({ where: { tradingAccountId: acc.id, active: true }, data: { active: false } })
  const created = await db.riskLimit.create({
    data: {
      tradingAccountId: acc.id,
      version: nextVersion,
      maxPositionSize: body.maxPositionSize ?? prev?.maxPositionSize ?? '10',
      maxLeverage: body.maxLeverage ?? prev?.maxLeverage ?? '30',
      maxDailyLossPct: body.maxDailyLossPct ?? prev?.maxDailyLossPct ?? '5',
      maxWeeklyLossPct: body.maxWeeklyLossPct ?? prev?.maxWeeklyLossPct ?? '10',
      maxDrawdownPct: body.maxDrawdownPct ?? prev?.maxDrawdownPct ?? '20',
      maxAggregateExposure: body.maxAggregateExposure ?? prev?.maxAggregateExposure ?? '50000',
      maxSimultaneousPositions: body.maxSimultaneousPositions ?? prev?.maxSimultaneousPositions ?? 10,
      maxSpreadPips: body.maxSpreadPips ?? prev?.maxSpreadPips ?? '5',
      maxSlippagePips: body.maxSlippagePips ?? prev?.maxSlippagePips ?? '3',
      active: true,
    },
  })
  await audit({ userId: user.id, action: 'RISK_LIMIT_UPDATE', entity: 'RiskLimit', entityId: created.id, before: prev, after: created })
  return json({ limit: created })
}
