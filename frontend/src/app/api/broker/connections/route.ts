import { NextRequest } from 'next/server'
import { db } from '@/lib/db'
import { json, err, requireUser } from '@/lib/api'
import { audit } from '@/lib/audit'

export async function GET(req: NextRequest) {
  const user = await requireUser()
  if (!user) return err('Unauthorized', 401)
  const { searchParams } = new URL(req.url)
  const accountId = searchParams.get('accountId')
  if (!accountId) return err('accountId required')
  const acc = await db.tradingAccount.findFirst({ where: { id: accountId, userId: user.id } })
  if (!acc) return err('Account not found', 404)
  const conns = await db.brokerConnection.findMany({ where: { tradingAccountId: acc.id }, orderBy: { createdAt: 'desc' } })
  return json({ connections: conns })
}

export async function POST(req: NextRequest) {
  const user = await requireUser()
  if (!user) return err('Unauthorized', 401)
  const body = await req.json().catch(() => ({}))
  const accountId = body.accountId
  const broker = body.broker
  const mode = body.mode || 'DEMO'
  if (!accountId || !broker) return err('accountId and broker required')
  const acc = await db.tradingAccount.findFirst({ where: { id: accountId, userId: user.id } })
  if (!acc) return err('Account not found', 404)
  // LIVE connections are never auto-authorized; status starts CONNECTED with READ perms only.
  const isLive = mode === 'LIVE' || broker === 'DERIV_LIVE'
  const conn = await db.brokerConnection.create({
    data: {
      tradingAccountId: acc.id,
      broker,
      mode,
      status: 'CONNECTED',
      accountRef: body.accountRef || null,
      permissions: isLive ? 'READ' : 'TRADE',
      lastCheckedAt: new Date(),
    },
  })
  await audit({ userId: user.id, action: 'BROKER_CONNECT', entity: 'BrokerConnection', entityId: conn.id, after: { broker, mode, permissions: conn.permissions } })
  return json({ connection: conn })
}

// Revoke a broker connection (credential rotation / revocation).
export async function DELETE(req: NextRequest) {
  const user = await requireUser()
  if (!user) return err('Unauthorized', 401)
  const { searchParams } = new URL(req.url)
  const connId = searchParams.get('id')
  if (!connId) return err('id required')
  const conn = await db.brokerConnection.findUnique({ where: { id: connId }, include: { account: true } })
  if (!conn) return err('Connection not found', 404)
  if (conn.account.userId !== user.id) return err('Forbidden', 403)
  const updated = await db.brokerConnection.update({ where: { id: connId }, data: { status: 'REVOKED', permissions: 'READ' } })
  await audit({ userId: user.id, action: 'BROKER_REVOKE', entity: 'BrokerConnection', entityId: connId })
  return json({ connection: updated })
}
