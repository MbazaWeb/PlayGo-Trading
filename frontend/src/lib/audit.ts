// audit.ts — Immutable audit log helper.
import { db } from '@/lib/db'

export type AuditInput = {
  userId?: string
  action: string
  entity?: string
  entityId?: string
  before?: unknown
  after?: unknown
  ip?: string
}

export async function audit(input: AuditInput) {
  try {
    await db.auditLog.create({
      data: {
        userId: input.userId ?? null,
        action: input.action,
        entity: input.entity ?? null,
        entityId: input.entityId ?? null,
        before: input.before ? JSON.stringify(input.before) : null,
        after: input.after ? JSON.stringify(input.after) : null,
        ip: input.ip ?? null,
      },
    })
  } catch (e) {
    // Audit must never break the request flow, but we log loudly.
    console.error('[audit] failed to write audit log', input.action, e)
  }
}

// Append a trade event (order lifecycle). Never updated/deleted.
export async function recordTradeEvent(orderId: string, type: string, payload: unknown) {
  await db.tradeEvent.create({
    data: {
      orderId,
      type,
      payload: JSON.stringify(payload ?? {}),
    },
  })
}
