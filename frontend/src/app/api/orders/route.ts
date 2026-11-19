import { NextRequest } from 'next/server'
import { db } from '@/lib/db'
import { json, err, requireUser, parseBody } from '@/lib/api'
import { createOrder, markToMarket, genClientOrderId } from '@/lib/execution'
import { audit } from '@/lib/audit'

export async function GET(req: NextRequest) {
  const user = await requireUser()
  if (!user) return err('Unauthorized', 401)
  const { searchParams } = new URL(req.url)
  const accountId = searchParams.get('accountId')
  if (!accountId) return err('accountId required')
  const acc = await db.tradingAccount.findFirst({ where: { id: accountId, userId: user.id } })
  if (!acc) return err('Account not found', 404)
  // Refresh MTM before listing.
  await markToMarket(acc.id)
  const orders = await db.order.findMany({
    where: { tradingAccountId: acc.id },
    orderBy: { createdAt: 'desc' },
    take: 100,
    include: { instrument: true },
  })
  return json({ orders })
}

export async function POST(req: NextRequest) {
  const user = await requireUser()
  if (!user) return err('Unauthorized', 401)
  const body = await parseBody<{
    accountId?: string; symbol?: string; side?: 'BUY' | 'SELL'; type?: 'MARKET' | 'LIMIT' | 'STOP';
    size?: string | number; price?: string | number | null; stopLoss?: string | number | null;
    takeProfit?: string | number | null; clientOrderId?: string;
  }>(req)
  if (!body.accountId || !body.symbol || !body.side || !body.size) return err('Missing required fields.')
  const acc = await db.tradingAccount.findFirst({ where: { id: body.accountId, userId: user.id } })
  if (!acc) return err('Account not found', 404)
  const clientOrderId = body.clientOrderId || genClientOrderId()
  try {
    const result = await createOrder({
      tradingAccountId: acc.id,
      userId: user.id,
      clientOrderId,
      symbol: body.symbol,
      side: body.side,
      type: body.type || 'MARKET',
      size: body.size,
      price: body.price ?? null,
      stopLoss: body.stopLoss ?? null,
      takeProfit: body.takeProfit ?? null,
    })
    await audit({ userId: user.id, action: 'ORDER_CREATE', entity: 'Order', entityId: result.order?.id, after: { symbol: body.symbol, side: body.side, size: body.size, status: result.order?.status } })
    return json(result)
  } catch (e) {
    return err((e as Error).message, 400)
  }
}
