// PlayGo Trading — Production Worker (mini-service)
//
// A continuously-running Bun process that drives scheduled trading-engine work
// that is NOT suitable for serverless:
//   - every MTM_INTERVAL_MS: mark-to-market across all PAPER/DEMO accounts
//     (refreshes unrealized P&L, triggers SL/TP auto-close)
//   - daily at RECON_HOUR:00 UTC: run the Phase A reconciliation
//
// It calls the main app's token-protected internal endpoint:
//   POST http://localhost:3000/api/internal/worker
//   header: X-Worker-Token: <PLAYGO_WORKER_TOKEN>
//
// It exposes its own health endpoint on port WORKER_PORT (3001) for monitoring.
//
// Per the gateway rules, cross-service API calls use the relative path with
// ?XTransformPort only when going THROUGH the gateway. This worker runs on the
// same host and calls localhost:3000 directly (internal), which is permitted
// for a same-host worker.

const APP_BASE = process.env.PLAYGO_APP_URL || 'http://localhost:3000'
const WORKER_TOKEN = process.env.PLAYGO_WORKER_TOKEN || 'dev-worker-token-rotate-me'
const WORKER_PORT = parseInt(process.env.WORKER_PORT || '3001', 10)
const MTM_INTERVAL_MS = parseInt(process.env.MTM_INTERVAL_MS || String(30_000), 10)
const RECON_HOUR_UTC = parseInt(process.env.RECON_HOUR_UTC || '6', 10) // 06:00 UTC = 09:00 Nairobi

let lastMtm: { at: string; ok: boolean; accounts?: number; error?: string } = { at: '', ok: false }
let lastRecon: { at: string; ok: boolean; accounts?: number; error?: string } = { at: '', ok: false }
let lastReconDate = ''

async function callWorker(reconcile: boolean) {
  const url = `${APP_BASE}/api/internal/worker`
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Worker-Token': WORKER_TOKEN },
    body: JSON.stringify({ reconcile }),
  })
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(`worker call ${res.status}: ${text.slice(0, 200)}`)
  }
  return await res.json()
}

async function runMtm() {
  try {
    const d = await callWorker(false)
    lastMtm = { at: new Date().toISOString(), ok: true, accounts: d.accounts?.length ?? 0 }
    console.log(`[mtm] ${lastMtm.at} ok accounts=${lastMtm.accounts}`)
  } catch (e) {
    lastMtm = { at: new Date().toISOString(), ok: false, error: String((e as Error).message) }
    console.error(`[mtm] ${lastMtm.at} FAIL ${lastMtm.error}`)
  }
}

async function runRecon() {
  try {
    const d = await callWorker(true)
    const clean = (d.accounts ?? []).filter((a: { recon?: { status: string } }) => a.recon?.status === 'CLEAN').length
    lastRecon = { at: new Date().toISOString(), ok: true, accounts: clean }
    lastReconDate = new Date().toISOString().slice(0, 10)
    console.log(`[recon] ${lastRecon.at} ok cleanAccounts=${clean}/${d.accounts?.length ?? 0}`)
  } catch (e) {
    lastRecon = { at: new Date().toISOString(), ok: false, error: String((e as Error).message) }
    console.error(`[recon] ${lastRecon.at} FAIL ${lastRecon.error}`)
  }
}

// MTM loop
setInterval(runMtm, MTM_INTERVAL_MS)

// Reconciliation scheduler — checks every minute, fires once per day at RECON_HOUR_UTC.
let reconFiredForHour = -1
setInterval(() => {
  const now = new Date()
  const hourUTC = now.getUTCHours()
  if (hourUTC === RECON_HOUR_UTC && reconFiredForHour !== hourUTC) {
    reconFiredForHour = hourUTC
    runRecon()
  } else if (hourUTC !== RECON_HOUR_UTC) {
    reconFiredForHour = -1
  }
}, 60_000)

// Fire one MTM immediately on startup.
runMtm()

// Health HTTP server on WORKER_PORT.
const server = Bun.serve({
  port: WORKER_PORT,
  fetch(req) {
    const url = new URL(req.url)
    if (url.pathname === '/health' || url.pathname === '/') {
      return Response.json({
        ok: true,
        service: 'playgo-worker',
        port: WORKER_PORT,
        appBase: APP_BASE,
        mtmIntervalMs: MTM_INTERVAL_MS,
        reconHourUtc: RECON_HOUR_UTC,
        lastMtm,
        lastRecon,
        lastReconDate,
        uptimeSec: Math.round(process.uptime()),
      })
    }
    return new Response('Not Found', { status: 404 })
  },
})

console.log(`[playgo-worker] listening on :${WORKER_PORT} · app=${APP_BASE} · mtm every ${MTM_INTERVAL_MS}ms · recon daily ${String(RECON_HOUR_UTC).padStart(2, '0')}:00 UTC`)

export {}
