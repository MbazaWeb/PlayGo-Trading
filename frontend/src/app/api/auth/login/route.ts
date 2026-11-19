import { NextRequest, NextResponse } from 'next/server'
import { backendRequest } from '@/lib/backend'

export async function POST(req: NextRequest) {
  const body = await req.json().catch(() => ({})) as { username?: string; email?: string; password?: string }
  const username = (body.username || body.email || '').trim()
  const password = body.password || ''
  if (!username || !password) {
    return NextResponse.json({ error: 'Username and password required.' }, { status: 400 })
  }

  const result = await backendRequest<{ access_token?: string; detail?: string }>('/api/identity/login', {
    method: 'POST',
    body: { username, password },
  })
  if (!result.ok || !result.data.access_token) {
    return NextResponse.json(
      { error: typeof result.data.detail === 'string' ? result.data.detail : 'Authentication failed.' },
      { status: result.status },
    )
  }

  const response = NextResponse.json({
    user: { id: 'owner', email: username, name: null, role: 'OWNER' },
  })
  response.cookies.set('playgo_session', result.data.access_token, {
    httpOnly: true,
    sameSite: 'lax',
    secure: process.env.NODE_ENV === 'production',
    path: '/',
    expires: new Date(Date.now() + 8 * 60 * 60 * 1000),
  })
  return response
}
