const backendUrl = (process.env.PLAYGO_API_URL || process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8001')
  .trim()
  .replace(/\/$/, '')

export async function backendRequest<T = unknown>(
  path: string,
  options: { method?: string; token?: string; body?: unknown } = {},
): Promise<{ ok: boolean; status: number; data: T }> {
  const response = await fetch(`${backendUrl}${path}`, {
    method: options.method || 'GET',
    cache: 'no-store',
    headers: {
      ...(options.token ? { Authorization: `Bearer ${options.token}` } : {}),
      ...(options.body !== undefined ? { 'Content-Type': 'application/json' } : {}),
    },
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  })
  const data = await response.json().catch(() => ({})) as T
  return { ok: response.ok, status: response.status, data }
}
