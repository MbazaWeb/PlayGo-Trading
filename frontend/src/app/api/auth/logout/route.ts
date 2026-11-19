import { cookies } from 'next/headers'
import { NextResponse } from 'next/server'
import { backendRequest } from '@/lib/backend'

export async function POST() {
  const store = await cookies()
  const token = store.get('playgo_session')?.value
  if (token) await backendRequest('/api/identity/logout', { token, method: 'POST' })
  store.delete('playgo_session')
  return NextResponse.json({ ok: true })
}
