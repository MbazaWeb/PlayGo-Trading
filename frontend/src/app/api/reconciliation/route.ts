import { NextRequest } from 'next/server'
import { json, err, requireUser } from '@/lib/api'
import { observationStatus } from '@/lib/reconciliation'
import { getDerivAdapter } from '@/lib/broker-deriv'
import { db } from '@/lib/db'

// GET /api/reconciliation?accountId=...&phase=A|B
// Returns the observation streak + target progress for Phase A (30 days) or
// Phase B (60 days). Phase B progress is 0 until a real DEMO broker is
// connected and recording observations.
export async function GET(req: NextRequest) {
  const user = await requireUser()
  if (!user) return err('Unauthorized', 401)
  const { searchParams } = new URL(req.url)
  const accountId = searchParams.get('accountId')
  const phase = (searchParams.get('phase') === 'B' ? 'B' : 'A') as 'A' | 'B'
  if (!accountId) return err('accountId required')
  const acc = await db.tradingAccount.findFirst({ where: { id: accountId, userId: user.id } })
  if (!acc) return err('Account not found', 404)
  const status = await observationStatus(acc.id, phase)
  // For Phase B, also report whether a DEMO broker is configured.
  const derivDemo = phase === 'B' ? getDerivAdapter('demo') : null
  return json({
    account: { id: acc.id, mode: acc.mode, liveAuthorized: acc.liveAuthorized },
    observation: status,
    phaseB: phase === 'B' ? {
      demoBrokerConfigured: derivDemo?.configured ?? false,
      demoBrokerLive: false, // becomes true when a real DEMO connection is supplying snapshots
      requirement: 'A real Deriv DEMO (or OANDA practice) account must be connected before Phase B observation can begin. The clock starts on the first real observation.',
    } : null,
  })
}
