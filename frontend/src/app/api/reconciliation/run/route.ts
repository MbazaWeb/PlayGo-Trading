// /api/reconciliation/run — Phase A daily reconciliation.
// Runs the real financial integrity checks and records a dated observation.
// One observation per calendar day (UTC); re-running same day updates the row.
import { NextRequest } from 'next/server'
import { db } from '@/lib/db'
import { json, err, requireUser } from '@/lib/api'
import { verifyIntegrity, trialBalance, cashBalance } from '@/lib/accounting'
import { markToMarket } from '@/lib/execution'
import { audit } from '@/lib/audit'

function todayUTC(): Date {
  const d = new Date()
  return new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate()))
}

export async function POST(req: NextRequest) {
  const user = await requireUser()
  if (!user) return err('Unauthorized', 401)
  const { searchParams } = new URL(req.url)
  const accountId = searchParams.get('accountId')
  if (!accountId) return err('accountId required')
  const acc = await db.tradingAccount.findFirst({ where: { id: accountId, userId: user.id } })
  if (!acc) return err('Account not found', 404)

  // Refresh mark-to-market before measuring.
  await markToMarket(acc.id)

  const integrity = await verifyIntegrity(acc.id)
  const tb = await trialBalance(acc.id)
  const cash = await cashBalance(acc.id)
  const positions = await db.position.count({ where: { tradingAccountId: acc.id, status: 'OPEN' } })
  const orders = await db.order.count({ where: { tradingAccountId: acc.id } })

  const balanced = tb.balanced && integrity.invalid === 0
  const discrepancies: string[] = []
  if (!tb.balanced) discrepancies.push(`trial_balance_unbalanced:debit=${tb.debit.toString()}:credit=${tb.credit.toString()}`)
  if (integrity.invalid > 0) discrepancies.push(`integrity_mismatches:${integrity.invalid}`)
  const status = balanced ? 'CLEAN' : 'DISCREPANCY'

  const today = todayUTC()
  // Upsert today's observation: delete existing for today, then create.
  await db.reconciliation.deleteMany({ where: { tradingAccountId: acc.id, date: today } })
  const rec = await db.reconciliation.create({
    data: {
      tradingAccountId: acc.id,
      date: today,
      internalBalance: cash.toFixed(2),
      internalPositions: positions,
      brokerPositions: positions, // PAPER: broker == internal
      discrepancies: discrepancies.length ? JSON.stringify(discrepancies) : null,
      status,
    },
  })
  await audit({ userId: user.id, action: 'RECONCILIATION_RUN', entity: 'Reconciliation', entityId: rec.id, after: { date: today.toISOString().slice(0, 10), status } })

  // Compute consecutive clean days ending today.
  const allObs = await db.reconciliation.findMany({
    where: { tradingAccountId: acc.id },
    orderBy: { date: 'desc' },
    take: 60,
  })
  let consecutive = 0
  const dayMs = 86400000
  for (let i = 0; i < allObs.length; i++) {
    const expected = new Date(today.getTime() - i * dayMs)
    const obs = allObs[i]
    if (obs.status === 'CLEAN' && obs.date.getTime() === expected.getTime()) {
      consecutive++
    } else {
      break
    }
  }
  const totalClean = allObs.filter(o => o.status === 'CLEAN').length

  return json({
    observation: {
      date: today.toISOString().slice(0, 10),
      status,
      internalBalance: cash.toFixed(2),
      internalPositions: positions,
      orderCount: orders,
      integrity: { checked: integrity.checked, valid: integrity.valid, invalid: integrity.invalid },
      trialBalance: { debit: tb.debit.toString(), credit: tb.credit.toString(), balanced: tb.balanced },
      discrepancies,
    },
    progress: {
      consecutiveCleanDays: consecutive,
      totalCleanObservations: totalClean,
      required: 30,
      phaseAReady: consecutive >= 30,
      nextScheduledRun: null as string | null,
    },
  })
}
