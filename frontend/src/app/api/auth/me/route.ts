import { cookies } from 'next/headers'
import { NextResponse } from 'next/server'
import { backendRequest } from '@/lib/backend'

export async function GET() {
  const store = await cookies()
  const token = store.get('playgo_session')?.value
  if (!token) return NextResponse.json({ user: null, account: null })

  const result = await backendRequest<{ user_id?: string; role?: string }>(
    '/api/identity/me/paper-account',
    { token },
  )
  if (!result.ok) return NextResponse.json({ user: null, account: null })

  return NextResponse.json({
    user: { id: result.data.user_id || 'owner', email: 'owner', name: null, role: result.data.role || 'OWNER' },
    account: { id: 'paper-owner-account', mode: 'PAPER' },
  })
}
