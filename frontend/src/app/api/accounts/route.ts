import { db } from '@/lib/db'
import { json, err, requireUser } from '@/lib/api'
import { audit } from '@/lib/audit'
import { postOpeningCapital } from '@/lib/accounting'

export async function GET() {
  const user = await requireUser()
  if (!user) return err('Unauthorized', 401)
  const accounts = await db.tradingAccount.findMany({
    where: { userId: user.id },
    orderBy: { createdAt: 'asc' },
    include: { brokerConns: true },
  })
  return json({ accounts })
}

export async function POST(req: Request) {
  const user = await requireUser()
  if (!user) return err('Unauthorized', 401)
  const body = await req.json().catch(() => ({}))
  const mode = (body.mode || 'PAPER') as string
  if (mode !== 'PAPER' && mode !== 'DEMO' && mode !== 'LIVE') return err('Invalid mode.')
  // LIVE accounts are never created with liveAuthorized=true.
  const acc = await db.tradingAccount.create({
    data: {
      userId: user.id,
      label: body.label || `${mode} Account`,
      mode,
      broker: body.broker || (mode === 'PAPER' ? 'PAPER' : mode === 'DEMO' ? 'DERIV_DEMO' : 'DERIV_LIVE'),
      currency: body.currency || 'USD',
      liveAuthorized: false,
    },
  })
  if (mode === 'PAPER') {
    await postOpeningCapital(acc.id, '10000.00', user.id)
    await db.riskLimit.create({
      data: {
        tradingAccountId: acc.id, version: 1, maxPositionSize: '10', maxLeverage: '30',
        maxDailyLossPct: '5', maxWeeklyLossPct: '10', maxDrawdownPct: '20',
        maxAggregateExposure: '50000', maxSimultaneousPositions: 10,
        maxSpreadPips: '5', maxSlippagePips: '3', active: true,
      },
    })
    await db.brokerConnection.create({
      data: { tradingAccountId: acc.id, broker: 'PAPER', mode: 'PAPER', status: 'CONNECTED', permissions: 'TRADE', lastCheckedAt: new Date() },
    })
  }
  await audit({ userId: user.id, action: 'ACCOUNT_CREATE', entity: 'TradingAccount', entityId: acc.id, after: { mode, label: acc.label } })
  return json({ account: acc })
}
