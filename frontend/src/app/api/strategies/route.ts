import { db } from '@/lib/db'
import { json, err, requireUser } from '@/lib/api'
import { audit } from '@/lib/audit'

export async function GET() {
  const strategies = await db.strategy.findMany({ orderBy: { createdAt: 'desc' }, include: { backtests: { orderBy: { createdAt: 'desc' }, take: 5 } } })
  return json({ strategies })
}

export async function POST(req: Request) {
  const user = await requireUser()
  if (!user) return err('Unauthorized', 401)
  const body = await req.json().catch(() => ({}))
  if (!body.name) return err('Strategy name required.')
  const strat = await db.strategy.create({
    data: {
      name: body.name,
      version: 1,
      description: body.description || null,
      entryRules: JSON.stringify(body.entryRules || {}),
      exitRules: JSON.stringify(body.exitRules || {}),
      positionSizing: JSON.stringify(body.positionSizing || {}),
      instruments: body.instruments || 'EUR/USD',
      timeframes: body.timeframes || 'M15',
      maxDrawdownPct: body.maxDrawdownPct || 20,
      status: 'DRAFT',
    },
  })
  await audit({ userId: user.id, action: 'STRATEGY_CREATE', entity: 'Strategy', entityId: strat.id })
  return json({ strategy: strat })
}
