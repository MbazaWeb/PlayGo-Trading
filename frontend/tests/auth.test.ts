// auth.test.ts — Credentials + DB-backed sessions (pure + DB).
import { test, expect, describe, beforeAll, afterAll } from 'bun:test'
import { db } from '@/lib/db'
import {
  hashPassword,
  verifyPassword,
  newSessionToken,
  rateLimit,
  createSession,
} from '@/lib/auth'
import { createTestUser, cleanupTestUser, uniq } from './helpers'

describe('auth — credentials', () => {
  test("hashPassword('x') !== 'x'", async () => {
    const hash = await hashPassword('x')
    expect(hash).not.toBe('x')
    expect(hash.length).toBeGreaterThan(20) // bcrypt hashes are 60 chars
  })

  test("verifyPassword('x', hash) === true; verifyPassword('y', hash) === false", async () => {
    const hash = await hashPassword('x')
    expect(await verifyPassword('x', hash)).toBe(true)
    expect(await verifyPassword('y', hash)).toBe(false)
  })
})

describe('auth — newSessionToken', () => {
  test('returns a 64-char hex string', () => {
    const t = newSessionToken()
    expect(t).toMatch(/^[0-9a-f]{64}$/)
  })

  test('two calls produce different tokens', () => {
    const a = newSessionToken()
    const b = newSessionToken()
    expect(a).not.toBe(b)
  })
})

describe('auth — rateLimit', () => {
  test('first 20 calls ok, 21st returns ok:false', () => {
    const key = uniq('rl')
    for (let i = 0; i < 20; i++) {
      const r = rateLimit(key)
      expect(r.ok).toBe(true)
    }
    const blocked = rateLimit(key)
    expect(blocked.ok).toBe(false)
    expect(blocked.retryAfterMs).toBeGreaterThan(0)
  })

  test('different keys do not interfere', () => {
    const k1 = uniq('rl-a')
    const k2 = uniq('rl-b')
    for (let i = 0; i < 20; i++) rateLimit(k1)
    expect(rateLimit(k1).ok).toBe(false)
    expect(rateLimit(k2).ok).toBe(true) // fresh bucket
  })
})

describe('auth — createSession (DB)', () => {
  let userId: string

  beforeAll(async () => {
    const u = await createTestUser(uniq('auth'))
    userId = u.id
  })

  afterAll(async () => {
    await cleanupTestUser(userId)
  })

  test('createSession inserts a Session row linked to the user', async () => {
    const before = await db.session.count({ where: { userId } })
    const token = await createSession(userId)
    expect(token).toMatch(/^[0-9a-f]{64}$/)
    const after = await db.session.count({ where: { userId } })
    expect(after).toBe(before + 1)
    const row = await db.session.findUnique({ where: { token } })
    expect(row).not.toBeNull()
    expect(row!.userId).toBe(userId)
    expect(row!.expiresAt.getTime()).toBeGreaterThan(Date.now())
  })
})
