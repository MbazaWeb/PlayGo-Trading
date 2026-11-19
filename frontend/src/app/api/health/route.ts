import { json } from '@/lib/api'
import { db } from '@/lib/db'

export async function GET() {
  const components = await db.systemHealth.groupBy({
    by: ['component'],
    _max: { checkedAt: true },
  })
  const latest: Record<string, { status: string; message: string | null; checkedAt: Date } | null> = {}
  for (const c of components) {
    const row = await db.systemHealth.findFirst({ where: { component: c.component }, orderBy: { checkedAt: 'desc' } })
    latest[c.component] = row ? { status: row.status, message: row.message, checkedAt: row.checkedAt } : null
  }
  const overall = Object.values(latest).every(v => v?.status === 'OK') ? 'OK' : 'DEGRADED'
  return json({ status: overall, components: latest, version: '0.1.0-paper', liveTradingEnabled: false })
}
