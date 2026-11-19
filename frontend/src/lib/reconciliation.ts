// reconciliation.ts — Daily reconciliation engine for Phase A (PAPER) & Phase B (DEMO).
//
// What this does (per directive §A10 / §B5):
//   - Verifies accounting integrity (SHA-256 hashes match) for the account.
//   - Verifies the trial balance balances (sum debit === sum credit).
//   - Snapshots the internal cash balance + open-position count.
//   - Optionally compares against a broker-side snapshot (Phase B, when a DEMO
//     broker is connected).
//   - Records ONE Reconciliation row per (account, calendar day). Idempotent:
//     re-running on the same day upserts the existing row (does not duplicate,
//     does not back-fill past days).
//
// What this does NOT do:
//   - It never fabricates observations for dates that have not actually elapsed.
//   - It never simulates broker data. Phase B brokerBalance/brokerPositions are
//     null until a real DEMO broker connection supplies them.
import { db } from '@/lib/db'
import { Decimal } from 'decimal.js'
import { D, round } from '@/lib/money'
import { verifyIntegrity, trialBalance, cashBalance } from '@/lib/accounting'
import { getEmergencyStopState } from '@/lib/emergency'

export type ReconStatus = 'CLEAN' | 'DISCREPANCY' | 'BLOCKED'
export type ReconPhase = 'A' | 'B'

export type ReconInput = {
  tradingAccountId: string
  phase: ReconPhase
  // Optional broker-side snapshot for Phase B (demo). Null until a real DEMO
  // broker connection is live and supplying data.
  brokerBalance?: Decimal | null
  brokerPositions?: number | null
}

export type ReconResult = {
  date: Date
  status: ReconStatus
  internalBalance: Decimal
  brokerBalance: Decimal | null
  internalPositions: number
  brokerPositions: number | null
  discrepancies: string[]
  integrity: { checked: number; valid: number; invalid: number }
  trialBalance: { debit: Decimal; credit: Decimal; balanced: boolean }
  emergencyStopActive: boolean
  recorded: boolean // false if idempotent re-run on same day (upsert updated)
}

// Compute the current reconciliation state WITHOUT recording it.
export async function computeReconciliation(input: ReconInput): Promise<ReconResult> {
  const integ = await verifyIntegrity(input.tradingAccountId)
  const tb = await trialBalance(input.tradingAccountId)
  const cash = await cashBalance(input.tradingAccountId)
  const positions = await db.position.count({ where: { tradingAccountId: input.tradingAccountId, status: 'OPEN' } })
  const es = await getEmergencyStopState(input.tradingAccountId)

  const discrepancies: string[] = []
  if (!tb.balanced) discrepancies.push(`trial_balance_out_of_balance: debit=${tb.debit.toString()} credit=${tb.credit.toString()}`)
  if (integ.invalid > 0) discrepancies.push(`integrity_hash_mismatches: ${integ.invalid}`)
  if (input.brokerBalance !== null && input.brokerBalance !== undefined) {
    const diff = D(input.brokerBalance).minus(cash)
    if (diff.abs().gt(new Decimal('0.01'))) {
      discrepancies.push(`cash_vs_broker_balance: internal=${cash.toString()} broker=${input.brokerBalance.toString()} diff=${diff.toString()}`)
    }
  }
  if (input.brokerPositions !== null && input.brokerPositions !== undefined) {
    if (input.brokerPositions !== positions) {
      discrepancies.push(`position_count_vs_broker: internal=${positions} broker=${input.brokerPositions}`)
    }
  }

  let status: ReconStatus = 'CLEAN'
  if (discrepancies.length > 0) status = 'DISCREPANCY'
  // BLOCKED is reserved for when a prior DISCREPANCY is unresolved and blocking
  // new orders — the risk engine handles blocking; here we propagate DISCREPANCY.
  if (es.active && discrepancies.length === 0) {
    // Emergency stop active with no discrepancies is still CLEAN (operator chose to stop).
  }

  // The "date" is the current calendar day in UTC, truncated to midnight.
  const now = new Date()
  const date = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()))

  return {
    date,
    status,
    internalBalance: round(cash, 2),
    brokerBalance: input.brokerBalance ?? null,
    internalPositions: positions,
    brokerPositions: input.brokerPositions ?? null,
    discrepancies,
    integrity: { checked: integ.checked, valid: integ.valid, invalid: integ.invalid },
    trialBalance: { debit: tb.debit, credit: tb.credit, balanced: tb.balanced },
    emergencyStopActive: es.active,
    recorded: false,
  }
}

// Record today's observation for an account. Idempotent per (account, date):
// if a row already exists for today, it is updated in place (re-verified).
// Never creates rows for past or future dates.
export async function recordDailyReconciliation(input: ReconInput): Promise<ReconResult & { id: string }> {
  const computed = await computeReconciliation(input)
  const row = await db.reconciliation.upsert({
    where: { tradingAccountId_date: { tradingAccountId: input.tradingAccountId, date: computed.date } },
    create: {
      tradingAccountId: input.tradingAccountId,
      date: computed.date,
      internalBalance: computed.internalBalance.toString(),
      brokerBalance: computed.brokerBalance ? computed.brokerBalance.toString() : null,
      internalPositions: computed.internalPositions,
      brokerPositions: computed.brokerPositions ?? null,
      discrepancies: JSON.stringify(computed.discrepancies),
      status: computed.status,
      phase: input.phase,
    },
    update: {
      // Re-verify on same-day re-run: refresh the snapshot + status.
      internalBalance: computed.internalBalance.toString(),
      brokerBalance: computed.brokerBalance ? computed.brokerBalance.toString() : null,
      internalPositions: computed.internalPositions,
      brokerPositions: computed.brokerPositions ?? null,
      discrepancies: JSON.stringify(computed.discrepancies),
      status: computed.status,
    },
  })
  return { ...computed, id: row.id }
}

// Compute the Phase A/B observation streak for an account.
// A "clean day" is a recorded observation with status === 'CLEAN'.
// The streak counts CONSECUTIVE clean days ending at the most recent observation.
// The required target is configurable (30 for Phase A, 60 for Phase B).
export async function observationStatus(tradingAccountId: string, phase: ReconPhase, targetDays = phase === 'A' ? 30 : 60) {
  const rows = await db.reconciliation.findMany({
    where: { tradingAccountId, phase },
    orderBy: { date: 'asc' },
  })
  // Distinct days (defensive; unique constraint already enforces this).
  const days = rows
  const total = days.length
  const clean = days.filter(d => d.status === 'CLEAN').length
  const discrepancy = days.filter(d => d.status !== 'CLEAN').length
  // Consecutive clean streak ending at the last observation.
  let streak = 0
  for (let i = days.length - 1; i >= 0; i--) {
    if (days[i].status === 'CLEAN') streak++
    else break
  }
  const first = days[0]?.date ?? null
  const last = days[days.length - 1]?.date ?? null
  // Target completion date = first observation + targetDays (calendar days).
  const targetDate = first ? new Date(first.getTime() + targetDays * 24 * 60 * 60 * 1000) : null
  const complete = streak >= targetDays && discrepancy === 0
  return {
    phase,
    targetDays,
    recordedDays: total,
    cleanDays: clean,
    discrepancyDays: discrepancy,
    streak,
    firstObservation: first,
    lastObservation: last,
    targetDate,
    complete,
    remainingDays: Math.max(0, targetDays - streak),
    progressPct: total === 0 ? 0 : Number(Math.min(100, (streak / targetDays) * 100).toFixed(1)),
    observations: days.map(d => ({
      id: d.id,
      date: d.date,
      status: d.status,
      internalBalance: d.internalBalance.toString(),
      internalPositions: d.internalPositions,
      discrepancies: d.discrepancies ? JSON.parse(d.discrepancies) : [],
      recordedAt: d.createdAt,
    })),
  }
}
