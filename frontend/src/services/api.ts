import { DASHBOARD_PATHS, DashboardPage } from '../types/trading';

const configuredApi = (import.meta.env.VITE_API_URL || '').trim().replace(/\/$/, '');
export const API =
  configuredApi ||
  (['localhost', '127.0.0.1'].includes(window.location.hostname)
    ? 'http://127.0.0.1:8001'
    : 'https://playgo-ai-trading-api.vercel.app');

export const SESSION_KEY = 'playgo_owner_session';
export const HANDOFF_KEY = 'playgo_deriv_signin_handoff';
export const TRADE_AMOUNT_KEY = 'playgo_paper_trade_amount_usd';

export const randomSecret = () =>
  btoa(String.fromCharCode(...crypto.getRandomValues(new Uint8Array(32))))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '');

export function getPageFromPath(pathname = window.location.pathname): DashboardPage {
  const clean = pathname.replace(/\/+$/, '') || '/';
  switch (clean) {
    case DASHBOARD_PATHS.market:
      return 'market';
    case DASHBOARD_PATHS['trade-bot']:
      return 'trade-bot';
    case DASHBOARD_PATHS['pnl-hedge']:
      return 'pnl-hedge';
    case DASHBOARD_PATHS.agents:
      return 'agents';
    default:
      return 'account';
  }
}

export async function apiRequest<T = any>(
  path: string,
  token = '',
  method = 'GET',
  body?: unknown
): Promise<T> {
  const response = await fetch(API + path, {
    method,
    cache: 'no-store',
    headers: {
      ...(token ? { Authorization: 'Bearer ' + token } : {}),
      ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(
      response.status === 401
        ? 'SESSION_EXPIRED'
        : typeof data.detail === 'string'
        ? data.detail
        : 'HTTP ' + response.status
    );
  }
  return data as T;
}
