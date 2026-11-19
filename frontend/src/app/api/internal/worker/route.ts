// /api/internal/worker — token-protected system endpoint for the production worker.
// The worker (mini-services/playgo-worker) calls this on a schedule to:
//   - run mark-to-market across all PAPER/DEMO accounts (refreshes unrealized + SL/TP)
//   - optionally run the daily Phase A reconciliation
//
// Auth: requires X-Worker-Token header matching process.env.PLAYGO_WORKER_TOKEN.
// This is NOT a user-facing endpoint; it never accepts user credentials.
import { NextRequest } from 'next/server'
import { db } from '@/lib/db'
import { json, err } from '@/lib/api'
import { markToMarket } from '@/lib/execution'
import { verifyIntegrity, trialBalance, cashBalance } from '@/lib/accounting'
import { audit } from '@/lib/audit'

function todayUTC(): Date {
  const d = new Date()
  return new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate()))
}

export async function POST(req: NextRequest) {
  const token = req.headers.get('x-worker-token')
  const expected = process.env.PLAYGO_WORKER_TOKEN
  if (!expected || token !== expected) {
    return err('Unauthorized', 401)
  }
  const body = await req.json().catch(() => ({}))
  const runReconciliation = body.reconcile === true

  const accounts = await db.tradingAccount.findMany({ where: { mode: { in: ['PAPER', 'DEMO'] } } })
  const results: Array<{ accountId: string; label: string; mtm: string; positions: number; recon?: { status: string; consecutive: number } }> = []

  for (const acc of accounts) {
    try {
      await markToMarket(acc.id)
      const positions = await db.position.count({ where: { tradingAccountId: acc.id, status: 'OPEN' } })
      let recon: { status: string; consecutive: number } | undefined
      if (runReconciliation) {
        const integrity = await verifyIntegrity(acc.id)
        const tb = await trialBalance(acc.id)
        const cash = await cashBalance(acc.id)
        const posCount = await db.position.count({ where: { tradingAccountId: acc.id, status: 'OPEN' } })
        const balanced = tb.balanced && integrity.invalid === 0
        const status = balanced ? 'CLEAN' : 'DISCREPANCY'
        const today = todayUTC()
        await db.reconciliation.deleteMany({ where: { tradingAccountId: acc.id, date: today } })
        await db.reconciliation.create({
          data: {
            tradingAccountId: acc.id, date: today,
            internalBalance: cash.toFixed(2), internalPositions: posCount, brokerPositions: posCount,
            discrepancies: balanced ? null : JSON.stringify(['trial_unbalanced_or_integrity_mismatch']),
            status,
          },
        })
        // consecutive clean
        const allObs = await db.reconciliation.findMany({ where: { tradingAccountId: acc.id }, orderBy: { date: 'desc' }, take: 60 })
        let consecutive = 0
        for (let i = 0; i < allObs.length; i++) {
          const expected2 = new Date(today.getTime() - i * 86400000)
          if (allObs[i].status === 'CLEAN' && allObs[i].date.getTime() === expected2.getTime()) consecutive++
          else break
        }
        recon = { status, consecutive }
      }
      results.push({ accountId: acc.id, label: acc.label, mtm: 'ok', positions, recon })
    } catch (e) {
      results.push({ accountId: acc.id, label: acc.label, mtm: 'error', positions: -1, recon: { status: String((e as Error).message), consecutive: 0 } })
    }
  }
  await audit({ action: 'WORKER_RUN', entity: 'system', after: { accounts: results.length, reconciled: runReconciliation } })
  return json({ ok: true, accounts: results, reconciled: runReconciliation })
}

export async function GET() {
  return json({ ok: true, service: 'playgo-worker-internal', requiresToken: !!process.env.PLAYGO_WORKER_TOKEN })
}
