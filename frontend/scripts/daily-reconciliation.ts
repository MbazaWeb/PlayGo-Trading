// scripts/daily-reconciliation.ts
//
// Standalone daily reconciliation runner. Invoked by the scheduled cron job
// (daily, 23:00 Africa/Nairobi) OR manually. Records ONE real observation per
// (account, calendar day) for every PAPER account (Phase A) and every account
// with a live DEMO broker connection (Phase B).
//
// This script records REAL observations against the CURRENT database state on
// the ACTUAL day it runs. It never back-fills past dates and never fabricates
// future observations. Re-running on the same calendar day re-verifies and
// updates the existing row in place (idempotent upsert).
//
// Usage:  bun run scripts/daily-reconciliation.ts
import { db } from '../src/lib/db'
import { recordDailyReconciliation } from '../src/lib/reconciliation'
import { derivDemoSnapshot } from '../src/lib/broker-deriv'

async function main() {
  const accounts = await db.tradingAccount.findMany({ include: { brokerConns: true } })
  const today = new Date()
  const dateStr = new Date(Date.UTC(today.getUTCFullYear(), today.getUTCMonth(), today.getUTCDate())).toISOString()
  const results: { account: string; phase: string; status: string; date: string }[] = []

  for (const acc of accounts) {
    // Phase A: every PAPER account gets a daily observation.
    if (acc.mode === 'PAPER') {
      try {
        const r = await recordDailyReconciliation({ tradingAccountId: acc.id, phase: 'A' })
        results.push({ account: acc.id, phase: 'A', status: r.status, date: r.date.toISOString() })
        console.log(`[Phase A] account=${acc.id} status=${r.status} date=${r.date.toISOString()} integ(valid/checked)=${r.integrity.valid}/${r.integrity.checked} balanced=${r.trialBalance.balanced}`)
      } catch (e) {
        console.error(`[Phase A] account=${acc.id} FAILED`, e)
        results.push({ account: acc.id, phase: 'A', status: 'ERROR', date: dateStr })
      }
    }

    // Phase B: only accounts with a DEMO broker connection. The snapshot is
    // null until a real DEMO broker is live, so the observation is recorded
    // with null broker fields (clearly marked). The Phase B clock effectively
    // starts producing meaningful broker-validated rows only once the adapter
    // is live — but we still record the internal-only row so the streak is
    // honest about what was actually verified.
    const hasDemoConn = acc.brokerConns.some(c => c.mode === 'DEMO' && c.status !== 'REVOKED')
    if (acc.mode === 'DEMO' || hasDemoConn) {
      try {
        const snap = await derivDemoSnapshot()
        const r = await recordDailyReconciliation({
          tradingAccountId: acc.id, phase: 'B',
          brokerBalance: snap?.balance ?? null,
          brokerPositions: snap?.positions ?? null,
        })
        results.push({ account: acc.id, phase: 'B', status: r.status, date: r.date.toISOString() })
        console.log(`[Phase B] account=${acc.id} status=${r.status} date=${r.date.toISOString()} broker=${snap ? 'live' : 'not-configured'}`)
      } catch (e) {
        console.error(`[Phase B] account=${acc.id} FAILED`, e)
        results.push({ account: acc.id, phase: 'B', status: 'ERROR', date: dateStr })
      }
    }
  }

  console.log('\n=== Daily reconciliation complete ===')
  console.log(JSON.stringify({ runDate: dateStr, results }, null, 2))
  await db.$disconnect()
}

main().catch(async (e) => {
  console.error('Daily reconciliation script failed:', e)
  await db.$disconnect()
  process.exit(1)
})
