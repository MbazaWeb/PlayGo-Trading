// auth.ts — Credentials + DB-backed sessions.
// Passwords hashed with bcrypt. Sessions are opaque tokens stored in DB
// with an expiration. No JWTs to keep rotation/revocation simple and explicit.
import { db } from '@/lib/db'
import bcrypt from 'bcryptjs'
import { cookies } from 'next/headers'

export const SESSION_COOKIE = 'playgo_session'
const SESSION_TTL_MS = 1000 * 60 * 60 * 24 * 7 // 7 days

export async function hashPassword(plain: string): Promise<string> {
  return bcrypt.hash(plain, 12)
}

export async function verifyPassword(plain: string, hash: string): Promise<boolean> {
  return bcrypt.compare(plain, hash)
}

export function newSessionToken(): string {
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const crypto = require('crypto')
  return crypto.randomBytes(32).toString('hex')
}

export async function createSession(userId: string): Promise<string> {
  const token = newSessionToken()
  const expiresAt = new Date(Date.now() + SESSION_TTL_MS)
  await db.session.create({ data: { userId, token, expiresAt } })
  return token
}

export async function setSessionCookie(token: string) {
  const store = await cookies()
  store.set(SESSION_COOKIE, token, {
    httpOnly: true,
    sameSite: 'lax',
    secure: process.env.NODE_ENV === 'production',
    path: '/',
    expires: new Date(Date.now() + SESSION_TTL_MS),
  })
}

export async function clearSessionCookie() {
  const store = await cookies()
  store.delete(SESSION_COOKIE)
}

export async function getUserFromCookie(): Promise<{ id: string; email: string; name: string | null; role: string } | null> {
  const store = await cookies()
  const token = store.get(SESSION_COOKIE)?.value
  if (!token) return null
  const session = await db.session.findUnique({
    where: { token },
    include: { user: true },
  })
  if (!session) return null
  if (session.expiresAt.getTime() < Date.now()) {
    await db.session.delete({ where: { id: session.id } }).catch(() => {})
    return null
  }
  return {
    id: session.user.id,
    email: session.user.email,
    name: session.user.name,
    role: session.user.role,
  }
}

export async function destroySession(token: string) {
  await db.session.deleteMany({ where: { token } }).catch(() => {})
}

// Simple per-request rate limiter (in-memory, per process). Used to throttle
// login/register attempts. Production should use Redis or a durable store.
const buckets = new Map<string, { count: number; resetAt: number }>()
const RATE_LIMIT_WINDOW_MS = 60_000
const RATE_LIMIT_MAX = 20

export function rateLimit(key: string): { ok: boolean; retryAfterMs: number } {
  const now = Date.now()
  const b = buckets.get(key)
  if (!b || b.resetAt < now) {
    buckets.set(key, { count: 1, resetAt: now + RATE_LIMIT_WINDOW_MS })
    return { ok: true, retryAfterMs: 0 }
  }
  if (b.count >= RATE_LIMIT_MAX) {
    return { ok: false, retryAfterMs: b.resetAt - now }
  }
  b.count++
  return { ok: true, retryAfterMs: 0 }
}
