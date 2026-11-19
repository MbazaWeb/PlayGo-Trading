import { NextRequest } from 'next/server'
import { json, err, requireUser } from '@/lib/api'
import { getDerivAdapter } from '@/lib/broker-deriv'
import { db } from '@/lib/db'

// GET /api/reconciliation/demo
// Reports the Phase B DEMO broker readiness state: whether a DEMO broker is
// configured, whether it's live, and what's required to start the 60-90 day
// observation clock.
export async function GET(req: NextRequest) {
  const user = await requireUser()
  if (!user) return err('Unauthorized', 401)
  const { searchParams } = new URL(req.url)
  const accountId = searchParams.get('accountId')
  if (!accountId) return err('accountId required')
  const acc = await db.tradingAccount.findFirst({ where: { id: accountId, userId: user.id } })
  if (!acc) return err('Account not found', 404)
  const derivDemo = getDerivAdapter('demo')
  const demoConn = await db.brokerConnection.findFirst({
    where: { tradingAccountId: acc.id, mode: 'DEMO' },
    orderBy: { createdAt: 'desc' },
  })
  return json({
    demoBroker: {
      configured: derivDemo.configured,
      adapterImplemented: false, // true only when the WebSocket adapter is production-ready
      live: false, // true only when a real DEMO connection is supplying snapshots
    },
    brokerConnection: demoConn ? {
      id: demoConn.id, broker: demoConn.broker, status: demoConn.status, permissions: demoConn.permissions,
    } : null,
    requirements: [
      'Create a Deriv DEMO (virtual) account or an OANDA practice account.',
      'Generate a DEMO API token at the broker (distinct from any LIVE token).',
      'Provide the DEMO token via server-side secret management (DERIV_DEMO_TOKEN env / vault), never in chat or committed code.',
      'Connect the DEMO broker via the Broker Connections view (mode=DEMO).',
      'Implement the production Deriv WebSocket adapter in a persistent worker process.',
      'Once live, the daily reconciliation cron records real DEMO observations; the 60-90 day clock starts on the first observation.',
    ],
    blocked: true,
    blockReason: 'No real DEMO broker connection is live. Phase B observation clock cannot start.',
  })
}
