// broker-deriv.ts — Deriv broker adapter scaffold (DEMO + LIVE).
//
// STATUS: SCAFFOLD. This implements the adapter *interface* and the connection
// plumbing shape. It does NOT contain any real API token. The user must supply
// a DEMO account token via server-side secret management (env var / vault),
// never in the database, never in frontend code, never committed to git.
//
// IMPORTANT: The Deriv token shared in the user's development paste is treated
// as a LIVE/production credential and is NOT used here. A separate DEMO account
// token must be created by the user at Deriv and provided through a secure
// channel. Phase B observation cannot start until a real DEMO connection is
// live and supplying real broker-side snapshots.
//
// Deriv API: WebSocket-based at wss://ws.derivws.com/websockets/v3?app_id=<APP_ID>
// (or the demo endpoint). A production adapter should run in a persistent worker
// process, not serverless (per directive §8).
import { Decimal } from 'decimal.js'

export type DerivEnv = 'demo' | 'live'

export type DerivConfig = {
  appId: string      // from DERIV_APP_ID env, NOT hardcoded
  token: string      // from DERIV_API_TOKEN (demo) or DERIV_LIVE_TOKEN env, NOT hardcoded
  env: DerivEnv
}

export type DerivAccountInfo = {
  loginid: string
  currency: string
  balance: Decimal
  equity: Decimal
  margin: Decimal
  isVirtual: boolean // true for demo accounts
}

export type DerivPosition = {
  symbol: string
  side: 'BUY' | 'SELL'
  size: Decimal
  entryPrice: Decimal
  currentPrice: Decimal
  unrealizedPnl: Decimal
}

// Load a Deriv config from environment. Returns null if the required env vars
// are absent — the caller treats this as "no DEMO broker configured".
export function loadDerivConfig(env: DerivEnv = 'demo'): DerivConfig | null {
  const appId = process.env.DERIV_APP_ID
  // DEMO uses DERIV_API_TOKEN (a demo/virtual-account token).
  // LIVE uses DERIV_LIVE_TOKEN (separate, gated, never auto-loaded).
  const token = env === 'live' ? process.env.DERIV_LIVE_TOKEN : process.env.DERIV_DEMO_TOKEN
  if (!appId || !token) return null
  return { appId, token, env }
}

// --- Adapter interface (stubs) ---
// Each method is documented with the Deriv API call it maps to. The actual
// WebSocket plumbing must be implemented in a persistent worker process.

export interface DerivAdapter {
  /** Authorize: { authorize: <token> }. Verifies the token + account. */
  authorize(): Promise<DerivAccountInfo>
  /** { account_list } / { balance } — current balance/equity/margin snapshot. */
  balance(): Promise<DerivAccountInfo>
  /** { portfolio } — open positions. */
  openPositions(): Promise<DerivPosition[]>
  /** { profit_table } / { transaction_history } — closed trades. */
  closedTrades(limit: number): Promise<unknown[]>
  /** { active_symbols } — instrument metadata. */
  activeSymbols(): Promise<unknown[]>
  /** { ticks_history } / { candles } — historical OHLCV. */
  candles(symbol: string, granularity: number, count: number): Promise<unknown[]>
  /** { buy } — place a contract. LIVE requires all Phase C gates + human auth. */
  buy(params: unknown): Promise<{ orderId: string; status: string }>
  /** { sell } — close a contract. */
  sell(contractId: string): Promise<{ status: string }>
  /** Health: ping + connection state. */
  health(): Promise<{ connected: boolean; latencyMs: number }>
}

// Factory: returns a stub adapter that reports "not configured" until real
// credentials are present. This lets the reconciliation endpoint safely call
// into the adapter without crashing when DEMO isn't set up yet.
export function getDerivAdapter(env: DerivEnv = 'demo'): { configured: boolean; adapter: DerivAdapter | null } {
  const cfg = loadDerivConfig(env)
  if (!cfg) return { configured: false, adapter: null }
  // TODO(production): instantiate a real WebSocket-backed adapter here.
  // For now, return a not-implemented adapter so the interface is exercised.
  const adapter: DerivAdapter = {
    async authorize() { throw new Error('Deriv adapter not yet implemented — requires production WebSocket worker.') },
    async balance() { throw new Error('Deriv adapter not yet implemented.') },
    async openPositions() { throw new Error('Deriv adapter not yet implemented.') },
    async closedTrades() { throw new Error('Deriv adapter not yet implemented.') },
    async activeSymbols() { throw new Error('Deriv adapter not yet implemented.') },
    async candles() { throw new Error('Deriv adapter not yet implemented.') },
    async buy() { throw new Error('Deriv adapter not yet implemented. LIVE requires Phase C + human auth.') },
    async sell() { throw new Error('Deriv adapter not yet implemented.') },
    async health() { return { connected: false, latencyMs: -1 } },
  }
  return { configured: true, adapter }
}

// Fetch a real broker-side snapshot for Phase B reconciliation. Returns null
// when no DEMO broker is configured, so the reconciliation records a Phase B
// observation with null broker fields (clearly marked "no broker connected").
export async function derivDemoSnapshot(): Promise<{ balance: Decimal; positions: number } | null> {
  const { configured, adapter } = getDerivAdapter('demo')
  if (!configured || !adapter) return null
  try {
    const info = await adapter.balance()
    const positions = await adapter.openPositions()
    return { balance: info.balance, positions: positions.length }
  } catch {
    return null
  }
}
