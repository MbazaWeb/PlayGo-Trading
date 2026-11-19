// PlayGo Trading — Deriv DEMO Broker Adapter (mini-service, port 3002)
//
// Connects to Deriv's WebSocket API, authorizes with a token (from env), and
// performs READ-ONLY account inspection:
//   - account balance, currency, equity
//   - account_list with is_virtual flag (demo vs real)
//
// SAFETY (per directive):
//   - This adapter NEVER places trades. It is observation-only.
//   - If the authorized account is REAL (is_virtual === 0/1 === false), the
//     adapter flags it and refuses to even prepare trade operations. Only
//     demo (virtual) accounts are eligible for Phase B demo observation.
//   - The token is read from env (DERIV_API_TOKEN), NEVER hardcoded, NEVER
//     logged, NEVER returned by any endpoint.
//
// Env:
//   DERIV_APP_ID     — Deriv application id (e.g. 32hxfkzWYA2IiQoReM03s)
//   DERIV_API_TOKEN  — Deriv API token (demo or real). NOT committed.
//   DERIV_WS_URL     — optional override (default wss://ws.derivws.com/websockets/v3)
//   ADAPTER_PORT     — default 3002
//
// Health endpoint: GET http://localhost:3002/health
//   returns connection status, account type (demo/real), balance, isVirtual,
//   and lastError if the connection failed (e.g. network restricted).

const DERIV_APP_ID = process.env.DERIV_APP_ID || ''
const DERIV_API_TOKEN = process.env.DERIV_API_TOKEN || ''
const DERIV_WS_URL = process.env.DERIV_WS_URL || 'wss://ws.derivws.com/websockets/v3?app_id=' + DERIV_APP_ID
const PORT = parseInt(process.env.ADAPTER_PORT || '3002', 10)

type AdapterState = {
  status: 'UNCONFIGURED' | 'DISCONNECTED' | 'CONNECTING' | 'CONNECTED' | 'ERROR'
  isVirtual: boolean | null
  accountType: 'demo' | 'real' | 'unknown'
  loginid: string | null
  currency: string | null
  balance: string | null
  lastError: string | null
  lastCheckedAt: string | null
}

let state: AdapterState = {
  status: DERIV_APP_ID && DERIV_API_TOKEN ? 'DISCONNECTED' : 'UNCONFIGURED',
  isVirtual: null,
  accountType: 'unknown',
  loginid: null,
  currency: null,
  balance: null,
  lastError: null,
  lastCheckedAt: null,
}

let ws: WebSocket | null = null
let reconnectTimer: ReturnType<typeof setInterval> | null = null

function connect() {
  if (!DERIV_APP_ID || !DERIV_API_TOKEN) {
    state = { ...state, status: 'UNCONFIGURED', lastError: 'DERIV_APP_ID or DERIV_API_TOKEN not set in env' }
    return
  }
  state = { ...state, status: 'CONNECTING', lastError: null }
  try {
    ws = new WebSocket(DERIV_WS_URL)
  } catch (e) {
    state = { ...state, status: 'ERROR', lastError: 'WebSocket constructor failed: ' + String((e as Error).message) }
    return
  }
  ws.addEventListener('open', () => {
    // Authorize (read-only). Never send a "buy"/"sell" request from this adapter.
    ws!.send(JSON.stringify({ authorize: DERIV_API_TOKEN }))
  })
  ws.addEventListener('message', (ev) => {
    try {
      const msg = JSON.parse(typeof ev.data === 'string' ? ev.data : '{}')
      if (msg.authorize) {
        const a = msg.authorize
        state = {
          ...state,
          status: 'CONNECTED',
          isVirtual: !!a.is_virtual,
          accountType: a.is_virtual ? 'demo' : 'real',
          loginid: a.loginid || null,
          currency: a.currency || null,
          balance: a.balance != null ? String(a.balance) : null,
          lastCheckedAt: new Date().toISOString(),
          lastError: null,
        }
        console.log(`[deriv] authorized loginid=${a.loginid} is_virtual=${a.is_virtual} currency=${a.currency} balance=${a.balance}`)
        // If REAL account, flag loudly and refuse any further trade prep.
        if (!a.is_virtual) {
          console.warn(`[deriv] WARNING: authorized account ${a.loginid} is REAL (not virtual). Phase B demo observation requires a DEMO/virtual account. This adapter will remain read-only and will NOT place trades.`)
        }
        // Request account_list to confirm virtual status across all accounts under the token.
        ws!.send(JSON.stringify({ account_list: 1 }))
      } else if (msg.account_list) {
        const list = msg.account_list || []
        const anyReal = list.some((x: { is_virtual: boolean }) => !x.is_virtual)
        if (anyReal) {
          console.warn(`[deriv] account_list contains a REAL account. Read-only mode enforced.`)
        }
      } else if (msg.error) {
        state = { ...state, status: 'ERROR', lastError: msg.error.message || JSON.stringify(msg.error), lastCheckedAt: new Date().toISOString() }
        console.error('[deriv] error:', msg.error)
      }
    } catch (e) {
      // ignore parse errors
    }
  })
  ws.addEventListener('close', () => {
    state = { ...state, status: 'DISCONNECTED', lastCheckedAt: new Date().toISOString() }
    console.log('[deriv] connection closed; will retry in 15s')
  })
  ws.addEventListener('error', () => {
    state = { ...state, status: 'ERROR', lastError: 'WebSocket error (likely network restricted or unreachable endpoint)', lastCheckedAt: new Date().toISOString() }
    console.error('[deriv] websocket error — if this sandbox blocks outbound WSS, the adapter is ready but cannot reach Deriv from here')
  })
}

// Initial connect + reconnect loop.
connect()
reconnectTimer = setInterval(() => {
  if (state.status !== 'CONNECTED' && state.status !== 'CONNECTING' && state.status !== 'UNCONFIGURED') {
    connect()
  }
}, 15_000)

// Health HTTP server.
const server = Bun.serve({
  port: PORT,
  fetch(req) {
    const url = new URL(req.url)
    if (url.pathname === '/health' || url.pathname === '/') {
      // NEVER expose the token. Only derived, non-sensitive state.
      return Response.json({
        ok: state.status === 'CONNECTED',
        service: 'playgo-deriv-adapter',
        port: PORT,
        derivAppId: DERIV_APP_ID ? DERIV_APP_ID.slice(0, 4) + '…' : null,
        configured: !!(DERIV_APP_ID && DERIV_API_TOKEN),
        ...state,
        phaseBEligible: state.status === 'CONNECTED' && state.isVirtual === true,
        tradeCapable: false, // ALWAYS false — observation-only adapter
      })
    }
    if (url.pathname === '/state') {
      return Response.json(state)
    }
    return new Response('Not Found', { status: 404 })
  },
})

console.log(`[playgo-deriv-adapter] listening on :${PORT} · configured=${!!(DERIV_APP_ID && DERIV_API_TOKEN)} · ws=${DERIV_WS_URL.replace(/app_id=[^&]+/, 'app_id=…')}`)
console.log(`[playgo-deriv-adapter] OBSERVATION-ONLY: this adapter never places trades.`)

export {}
