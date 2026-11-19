import { json, err } from '@/lib/api'
import { seedIfEmpty } from '@/lib/seed'

// Development-only seed endpoint. Safe to call repeatedly (idempotent).
export async function POST() {
  if (process.env.NODE_ENV === 'production') {
    return err('Seed endpoint disabled in production.', 403)
  }
  const res = await seedIfEmpty()
  return json({ ok: true, user: { email: res.user.email }, account: { id: res.account.id, mode: res.account.mode } })
}
