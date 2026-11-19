// emergency.ts — Emergency stop service.
//
// The emergency stop:
//   - Blocks new entries immediately when active.
//   - Persists across process restarts (DB-backed).
//   - Is independently enforceable (checked by the execution engine before
//     any new order, regardless of frontend state).
//   - Requires explicit human action to reset (deactivate).
//   - Is audited.
//
// It does NOT automatically liquidate existing positions — that is a
// separate, documented position-management policy (see RISK_MANAGEMENT.md).
import { db } from '@/lib/db'
import { audit } from '@/lib/audit'

export async function isEmergencyStopActive(tradingAccountId: string): Promise<boolean> {
  const latest = await db.emergencyStop.findFirst({
    where: { tradingAccountId },
    orderBy: { createdAt: 'desc' },
  })
  return !!latest?.active
}

export async function activateEmergencyStop(tradingAccountId: string, userId: string, reason: string) {
  // Deactivate any prior active record for cleanliness, then create a new active one.
  await db.emergencyStop.updateMany({
    where: { tradingAccountId, active: true },
    data: { active: false, deactivatedAt: new Date() },
  })
  const es = await db.emergencyStop.create({
    data: { tradingAccountId, active: true, reason, activatedAt: new Date(), activatedBy: userId },
  })
  await audit({
    userId,
    action: 'EMERGENCY_STOP_ACTIVATE',
    entity: 'EmergencyStop',
    entityId: es.id,
    after: { tradingAccountId, reason },
  })
  return es
}

export async function deactivateEmergencyStop(tradingAccountId: string, userId: string) {
  const updated = await db.emergencyStop.updateMany({
    where: { tradingAccountId, active: true },
    data: { active: false, deactivatedAt: new Date() },
  })
  await audit({
    userId,
    action: 'EMERGENCY_STOP_DEACTIVATE',
    entity: 'EmergencyStop',
    after: { tradingAccountId, count: updated.count },
  })
  return updated
}

export async function getEmergencyStopState(tradingAccountId: string) {
  const latest = await db.emergencyStop.findFirst({
    where: { tradingAccountId },
    orderBy: { createdAt: 'desc' },
  })
  return {
    active: !!latest?.active,
    reason: latest?.reason ?? null,
    activatedAt: latest?.activatedAt ?? null,
    deactivatedAt: latest?.deactivatedAt ?? null,
  }
}
