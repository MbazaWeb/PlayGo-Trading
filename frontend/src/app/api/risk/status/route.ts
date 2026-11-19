import { NextRequest } from 'next/server'
import { json, err, requireUser } from '@/lib/api'
import { riskUtilization } from '@/lib/risk'
import { getEmergencyStopState } from '@/lib/emergency'
import { db } from '@/lib/db'

export async function GET(req: NextRequest) {
  const user = await requireUser()
  if (!user) return err('Unauthorized', 401)
  const { searchParams } = new URL(req.url)
  const accountId = searchParams.get('accountId')
  if (!accountId) return err('accountId required')
  const acc = await db.tradingAccount.findFirst({ where: { id: accountId, userId: user.id } })
  if (!acc) return err('Account not found', 404)
  const util = await riskUtilization(acc.id)
  const es = await getEmergencyStopState(acc.id)
  return json({
    account: { id: acc.id, mode: acc.mode, liveAuthorized: acc.liveAuthorized },
    utilization: util,
    emergencyStop: es,
    violations: util.netRealized.isNegative() ? Math.abs(Number(util.netRealized)) > Number(util.dailyLossLimit) ? ['daily_loss_limit_exceeded'] : [] : [],
  })
}
