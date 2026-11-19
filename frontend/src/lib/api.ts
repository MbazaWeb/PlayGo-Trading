// api.ts — shared API helpers.
import { NextResponse } from 'next/server'
import { getUserFromCookie } from '@/lib/auth'

export const json = (data: unknown, status = 200) => NextResponse.json(data, { status })

export const err = (message: string, status = 400, details?: unknown) =>
  NextResponse.json({ error: message, details }, { status })

export async function requireUser() {
  const user = await getUserFromCookie()
  if (!user) return null
  return user
}

export async function requireAdmin() {
  const user = await getUserFromCookie()
  if (!user || user.role !== 'ADMIN') return null
  return user
}

// Safely parse a JSON body.
export async function parseBody<T = Record<string, unknown>>(req: Request): Promise<T> {
  try {
    return (await req.json()) as T
  } catch {
    return {} as T
  }
}
