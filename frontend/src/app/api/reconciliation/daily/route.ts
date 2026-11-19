import { NextRequest } from 'next/server'
import { db } from '@/lib/db'
import { json, err, requireUser } from '@/lib/api'
import { recordDailyReconciliation } from '@/lib/reconciliation'
import { derivDemoSnapshot } from '@/lib/broker-deriv'
import { audit } from '@/lib/audit'

// POST /api/reconciliation/daily
// Runs today's reconciliation for an account (Phase A paper, or Phase B demo
// when a DEMO broker is connected). Idempotent per (account, day): re-running
// on the same day re-verifies and updates the existing row in place.
//
// This endpoint records REAL observations against the CURRENT database state.
// It never back-fills past dates.
export async function POST(req: NextRequest) {
  const user = await requireUser()
  if (!user) return err('Unauthorized', 401)
  const body = await req.json().catch(() => ({}))
  const accountId = body.accountId
  const phase: 'A' | 'B' = body.phase === 'B' ? 'B' : 'A'
  if (!accountId) return err('accountId required')
  const acc = await db.tradingAccount.findFirst({ where: { id: accountId, userId: user.id } })
  if (!acc) return err('Account not found', 404)

  // For Phase B, attempt a real broker snapshot if a DEMO broker is configured.
  let brokerBalance: import('decimal.js').Decimal | null = null
  let brokerPositions: number | null = null
  if (phase === 'B') {
    const snap = await derivDemoSnapshot()
    if (snap) {
      brokerBalance = snap.balance
      brokerPositions = snap.positions
    }
  }

  const result = await recordDailyReconciliation({
    tradingAccountId: acc.id,
    phase,
    brokerBalance,
    brokerPositions,
  })
  await audit({ userId: user.id, action: 'RECONCILIATION_RECORD', entity: 'Reconciliation', entityId: result.id, after: { phase, status: result.status, date: result.date } })
  return json({ result })
}
