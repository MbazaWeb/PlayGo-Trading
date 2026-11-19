// /api/reconciliation — list observations + Phase A progress.
import { NextRequest } from 'next/server'
import { db } from '@/lib/db'
import { json, err, requireUser } from '@/lib/api'

function todayUTC(): Date {
  const d = new Date()
  return new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate()))
}

export async function GET(req: NextRequest) {
  const user = await requireUser()
  if (!user) return err('Unauthorized', 401)
  const { searchParams } = new URL(req.url)
  const accountId = searchParams.get('accountId')
  if (!accountId) return err('accountId required')
  const acc = await db.tradingAccount.findFirst({ where: { id: accountId, userId: user.id } })
  if (!acc) return err('Account not found', 404)

  const observations = await db.reconciliation.findMany({
    where: { tradingAccountId: acc.id },
    orderBy: { date: 'desc' },
    take: 90,
  })

  const today = todayUTC()
  const dayMs = 86400000
  let consecutive = 0
  for (let i = 0; i < observations.length; i++) {
    const expected = new Date(today.getTime() - i * dayMs)
    const obs = observations[i]
    if (obs.status === 'CLEAN' && obs.date.getTime() === expected.getTime()) {
      consecutive++
    } else {
      break
    }
  }
  const totalClean = observations.filter(o => o.status === 'CLEAN').length
  const lastDiscrepancy = observations.find(o => o.status !== 'CLEAN') ?? null

  return json({
    observations: observations.map(o => ({
      id: o.id,
      date: o.date.toISOString().slice(0, 10),
      status: o.status,
      internalBalance: o.internalBalance.toString(),
      internalPositions: o.internalPositions,
      discrepancies: o.discrepancies,
      createdAt: o.createdAt,
    })),
    progress: {
      consecutiveCleanDays: consecutive,
      totalCleanObservations: totalClean,
      totalObservations: observations.length,
      required: 30,
      phaseAReady: consecutive >= 30,
      lastDiscrepancy: lastDiscrepancy ? { date: lastDiscrepancy.date.toISOString().slice(0, 10), status: lastDiscrepancy.status } : null,
      todayRecorded: observations[0]?.date.getTime() === today.getTime(),
    },
  })
}
