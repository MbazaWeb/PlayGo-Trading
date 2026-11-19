import { NextRequest } from 'next/server'
import { json, err, requireUser } from '@/lib/api'
import { verifyIntegrity } from '@/lib/accounting'

export async function GET(req: NextRequest) {
  const user = await requireUser()
  if (!user) return err('Unauthorized', 401)
  const { searchParams } = new URL(req.url)
  const accountId = searchParams.get('accountId')
  if (!accountId) return err('accountId required')
  const res = await verifyIntegrity(accountId)
  // Also verify the user owns the account.
  const acc = await import('@/lib/db').then(m => m.db.tradingAccount.findFirst({ where: { id: accountId, userId: user.id } }))
  if (!acc) return err('Account not found', 404)
  return json(res)
}
