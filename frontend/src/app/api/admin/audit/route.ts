import { NextRequest } from 'next/server'
import { db } from '@/lib/db'
import { json, err, requireAdmin } from '@/lib/api'

export async function GET(req: NextRequest) {
  const user = await requireAdmin()
  if (!user) return err('Unauthorized', 401)
  const { searchParams } = new URL(req.url)
  const limit = parseInt(searchParams.get('limit') || '200', 10)
  const action = searchParams.get('action')
  const logs = await db.auditLog.findMany({
    where: action ? { action } : {},
    orderBy: { createdAt: 'desc' },
    take: limit,
    include: { user: { select: { email: true, name: true } } },
  })
  return json({ logs })
}
