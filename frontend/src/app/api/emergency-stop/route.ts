import { NextRequest } from 'next/server'
import { db } from '@/lib/db'
import { json, err, requireUser } from '@/lib/api'
import { activateEmergencyStop, deactivateEmergencyStop, getEmergencyStopState } from '@/lib/emergency'

export async function GET(req: NextRequest) {
  const user = await requireUser()
  if (!user) return err('Unauthorized', 401)
  const { searchParams } = new URL(req.url)
  const accountId = searchParams.get('accountId')
  if (!accountId) return err('accountId required')
  const acc = await db.tradingAccount.findFirst({ where: { id: accountId, userId: user.id } })
  if (!acc) return err('Account not found', 404)
  const state = await getEmergencyStopState(acc.id)
  return json({ emergencyStop: state })
}

export async function POST(req: NextRequest) {
  const user = await requireUser()
  if (!user) return err('Unauthorized', 401)
  const body = await req.json().catch(() => ({}))
  const accountId = body.accountId
  const action = body.action // 'activate' | 'deactivate'
  const reason = body.reason || 'Manual activation'
  if (!accountId || !action) return err('accountId and action required')
  const acc = await db.tradingAccount.findFirst({ where: { id: accountId, userId: user.id } })
  if (!acc) return err('Account not found', 404)
  if (action === 'activate') {
    const es = await activateEmergencyStop(acc.id, user.id, reason)
    return json({ emergencyStop: es })
  } else if (action === 'deactivate') {
    const res = await deactivateEmergencyStop(acc.id, user.id)
    const state = await getEmergencyStopState(acc.id)
    return json({ result: res, emergencyStop: state })
  }
  return err('Invalid action')
}
