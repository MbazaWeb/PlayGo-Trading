import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Activity, ShieldCheck, LogOut } from 'lucide-react';
import './styles/real-account.css';
import {
  BotConfig,
  DASHBOARD_PATHS,
  DashboardPage,
  DemoBotState,
  NotificationCategory,
  NotificationLog,
  PAGE_TITLES,
  Snapshot,
} from './types/trading';
import { API, HANDOFF_KEY, SESSION_KEY, getPageFromPath, randomSecret } from './services/api';
import Navbar from './components/Navbar';
import NotificationPanel from './components/NotificationPanel';
import AccountPage from './pages/deriv/AccountPage';
import MarketPage from './pages/deriv/MarketPage';
import TradeBotPage from './pages/deriv/TradeBotPage';
import PnlHedgePage from './pages/deriv/PnlHedgePage';
import DerivMarketPanel from './DerivMarketPanel';

const NOTIF_STORAGE_KEY = 'playgo_notification_logs';

export default function AccountWorkspace() {
  const [oauthBusy, setOauthBusy] = useState(false);
  const [selectedId, setSelectedId] = useState('');
  const [token, setToken] = useState(() => sessionStorage.getItem(SESSION_KEY) || '');
  const [username, setUsername] = useState('playgo_admin');
  const [password, setPassword] = useState('');
  const [dashboardPage, setDashboardPage] = useState<DashboardPage>(() => getPageFromPath());
  const [data, setData] = useState<Snapshot | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [signingIn, setSigningIn] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const [botState, setBotState] = useState<DemoBotState | null>(null);
  const [botBusy, setBotBusy] = useState(false);
  const [botError, setBotError] = useState('');

  // Notification Logs State
  const [notifications, setNotifications] = useState<NotificationLog[]>(() => {
    try {
      const saved = localStorage.getItem(NOTIF_STORAGE_KEY);
      return saved ? (JSON.parse(saved) as NotificationLog[]) : [];
    } catch {
      return [];
    }
  });

  const [liveToast, setLiveToast] = useState<NotificationLog | null>(null);
  const toastTimerRef = useRef<number | undefined>(undefined);

  const pushNotification = useCallback(
    (category: NotificationCategory, title: string, message: string, amountLabel?: string, time = new Date().toISOString(), toast = true) => {
      const entry: NotificationLog = {
        id: 'notif-' + crypto.randomUUID(),
        category,
        title,
        message,
        amountLabel,
        time,
        read: false,
      };
      setNotifications((prev) => {
        const updated = [entry, ...prev].slice(0, 100);
        try {
          localStorage.setItem(NOTIF_STORAGE_KEY, JSON.stringify(updated));
        } catch {}
        return updated;
      });
      if (toast && (category === 'profit' || category === 'loss' || category === 'risk')) {
        setLiveToast(entry);
        window.clearTimeout(toastTimerRef.current);
        toastTimerRef.current = window.setTimeout(() => setLiveToast(null), 6000);
      }
    },
    []
  );

  const markAllRead = useCallback(() => {
    setNotifications((prev) => {
      const updated = prev.map((item) => ({ ...item, read: true }));
      try {
        localStorage.setItem(NOTIF_STORAGE_KEY, JSON.stringify(updated));
      } catch {}
      return updated;
    });
  }, []);

  const clearAllNotifications = useCallback(() => {
    setNotifications([]);
    try {
      localStorage.removeItem(NOTIF_STORAGE_KEY);
    } catch {}
  }, []);

  const derivSession = token.startsWith('deriv_');
  const selected =
    data?.accounts.find((account) => account.account_id === selectedId) ??
    data?.accounts.find((account) => account.account_type === (derivSession ? 'demo' : 'real')) ??
    data?.accounts[0];

  // Track Market Open / Closed Status Changes
  const marketStatusRef = useRef<Record<string, boolean>>({});
  useEffect(() => {
    if (!token) return;
    let active = true;
    async function checkMarketsStatus() {
      try {
        const res = await fetch(API + '/api/market/forex', {
          cache: 'no-store',
          headers: { Authorization: 'Bearer ' + token },
        });
        if (!res.ok) return;
        const body = await res.json();
        if (!active || !Array.isArray(body.markets)) return;

        for (const m of body.markets) {
          if (typeof m.symbol !== 'string' || typeof m.display_name !== 'string' ||
              typeof m.exchange_is_open !== 'boolean' || typeof m.is_trading_suspended !== 'boolean') continue;
          const isOpen = Boolean(m.exchange_is_open && !m.is_trading_suspended);
          const prevOpen = marketStatusRef.current[m.symbol];
          if (prevOpen !== undefined && prevOpen !== isOpen) {
            pushNotification(
              'market',
              isOpen ? `Market Open: ${m.display_name}` : `Market Closed: ${m.display_name}`,
              isOpen
                ? `${m.display_name} session is now open for trading.`
                : `${m.display_name} session has closed or is temporarily suspended.`
            );
          }
          marketStatusRef.current[m.symbol] = isOpen;
        }
      } catch {
        // silent background check
      }
    }
    void checkMarketsStatus();
    const timer = window.setInterval(() => void checkMarketsStatus(), 60000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [token, pushNotification]);

  // Track Bot Status Transitions (End / Risk / Error)
  const prevBotStatusRef = useRef<{ accountId: string; status: string; nearCap: boolean } | null>(null);
  useEffect(() => {
    if (!botState) return;
    const previous = prevBotStatusRef.current?.accountId === botState.account_id ? prevBotStatusRef.current : null;
    const currStatus = botState.status;

    if (previous?.status !== currStatus) {
      if (currStatus === 'needs_review') {
        pushNotification(
          'risk',
          'RISK ALERT: Trade Review Needed',
          'Bot paused because a trade outcome is uncertain. Verify your Deriv account before restarting.'
        );
      } else if (currStatus === 'daily_budget_reached') {
        pushNotification(
          'risk',
          'RISK / END: Daily Stake Limit Reached',
          `Bot reached its daily stake cap of USD ${Number(botState.daily_stake_limit).toFixed(2)} and ended execution.`
        );
      } else if (currStatus === 'insufficient_balance' || currStatus === 'feed_error') {
        pushNotification(
          'risk',
          'Demo bot paused',
          botState.last_error ?? currStatus.replace(/_/g, ' ')
        );
      }
    }

    // Warn when 80% of daily risk budget is used
    const used = Number(botState.daily_stake || 0);
    const limit = Number(botState.daily_stake_limit || 0);
    const nearCap = limit > 0 && used >= limit * 0.8;
    if (botState.running && nearCap && !previous?.nearCap) {
      pushNotification(
        'risk',
        'Risk Warning: 80% Daily Cap Used',
        `Used USD ${used.toFixed(2)} of your USD ${limit.toFixed(2)} daily stake cap.`
      );
    }

    prevBotStatusRef.current = { accountId: botState.account_id, status: currStatus, nearCap };
  }, [botState, pushNotification]);

  useEffect(() => {
    const cleanPath = window.location.pathname.replace(/\/+$/, '') || '/';
    if (cleanPath === '/') {
      window.history.replaceState(null, '', DASHBOARD_PATHS.account);
    }
    const syncPage = () => setDashboardPage(getPageFromPath());
    window.addEventListener('popstate', syncPage);
    return () => window.removeEventListener('popstate', syncPage);
  }, []);

  useEffect(() => {
    document.title = `${PAGE_TITLES[dashboardPage]} | PlayGo`;
  }, [dashboardPage]);

  const seenSettlements = useRef(new Map<string, Set<string>>());
  const publishSettlements = useCallback((body: {
    source?: string; account_id?: string; currency?: string;
    recent_closed?: { contract_id: string; symbol: string; profit: string; sell_time?: number | string | null }[];
  }, accountId: string) => {
    if (body.source !== 'DERIV' || body.account_id !== accountId ||
        typeof body.currency !== 'string' || !Array.isArray(body.recent_closed)) return;
    const key = `playgo_seen_settlements:${accountId}`;
    let seen = seenSettlements.current.get(accountId);
    if (!seen) {
      try {
        const saved: unknown = JSON.parse(localStorage.getItem(key) ?? '[]');
        seen = new Set(Array.isArray(saved) ? saved.filter((id) => typeof id === 'string') : []);
      } catch {
        seen = new Set();
      }
      seenSettlements.current.set(accountId, seen);
    }
    const initial = seen.size === 0;
    for (const row of body.recent_closed.slice(0, 500).reverse()) {
      if (!row || typeof row.contract_id !== 'string' || !row.contract_id ||
          typeof row.profit !== 'string' || !row.profit.trim() || seen.has(row.contract_id)) continue;
      const profit = Number(row.profit);
      if (!Number.isFinite(profit)) continue;
      seen.add(row.contract_id);
      if (profit === 0) continue;
      const time = row.sell_time;
      const timestamp = time == null ? NaN : /^\d+$/.test(String(time)) ? Number(time) * 1000 : Date.parse(String(time));
      const amount = `${profit > 0 ? '+' : '−'}${body.currency} ${Math.abs(profit).toFixed(2)}`;
      pushNotification(profit > 0 ? 'profit' : 'loss', profit > 0 ? 'Trade profit realized' : 'Trade loss realized',
        `${row.symbol || 'Deriv contract'} · #${row.contract_id}`, amount,
        Number.isFinite(timestamp) ? new Date(timestamp).toISOString() : undefined, !initial);
    }
    try {
      localStorage.setItem(key, JSON.stringify(Array.from(seen).slice(-1500)));
    } catch {}
  }, [pushNotification]);

  const loadMarkets = useCallback(
    async (path: string) => {
      const headers: HeadersInit = token ? { Authorization: 'Bearer ' + token } : {};
      const response = await fetch(API + path, { cache: 'no-store', headers });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw Error(typeof body.detail === 'string' ? body.detail : 'Unable to load Deriv market data.');
      }
      const accountId = selected?.account_id;
      if (accountId && path === `/api/deriv/accounts/${encodeURIComponent(accountId)}/performance`) {
        publishSettlements(body, accountId);
      }
      return body;
    },
    [token, selected?.account_id, publishSettlements]
  );

  useEffect(() => {
    const accountId = selected?.account_id;
    if (!token || !data?.connected || !accountId || dashboardPage === 'pnl-hedge' ||
        (dashboardPage === 'trade-bot' && derivSession && selected?.account_type === 'demo')) return;
    let inFlight = false;
    const poll = async () => {
      if (inFlight) return;
      inFlight = true;
      try {
        await loadMarkets(`/api/deriv/accounts/${encodeURIComponent(accountId)}/performance`);
      } catch {
        // Retry on the next poll.
      } finally {
        inFlight = false;
      }
    };
    void poll();
    const timer = window.setInterval(poll, 30_000);
    return () => window.clearInterval(timer);
  }, [dashboardPage, data?.connected, derivSession, loadMarkets, selected?.account_id, selected?.account_type, token]);

  async function signInWithDeriv() {
    setError('');
    const popup = window.open('about:blank', 'playgo-deriv-signin', 'popup,width=520,height=720');
    if (!popup) {
      setError('Allow popups for PlayGo, then try signing in again.');
      return;
    }
    setOauthBusy(true);
    try {
      const handoffId = randomSecret();
      const verifier = randomSecret();
      const hash = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(verifier));
      const challenge = btoa(String.fromCharCode(...new Uint8Array(hash)))
        .replace(/\+/g, '-')
        .replace(/\//g, '_')
        .replace(/=+$/, '');
      sessionStorage.setItem(HANDOFF_KEY, JSON.stringify({ handoffId, verifier, createdAt: Date.now() }));
      const params = new URLSearchParams({
        origin: window.location.origin,
        handoff_id: handoffId,
        handoff_challenge: challenge,
      });
      popup.opener = null;
      const authUrl = new URL('/api/deriv/oauth/signin', API || window.location.origin);
      authUrl.search = params.toString();
      popup.location.href = authUrl.toString();
      const deadline = Date.now() + 600000;
      let popupClosedAt = 0;
      while (Date.now() < deadline) {
        const response = await fetch(API + '/api/deriv/oauth/complete', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ handoff_id: handoffId, verifier }),
        });
        const body = await response.json();
        if (response.status === 202) {
          if (popup.closed) {
            if (!popupClosedAt) popupClosedAt = Date.now();
            if (Date.now() - popupClosedAt > 8000) throw Error('Sign-in was not completed. Please try again.');
          }
          await new Promise((resolve) => window.setTimeout(resolve, 750));
          continue;
        }
        if (!response.ok) {
          throw Error(typeof body.detail === 'string' ? body.detail : 'Unable to complete sign-in. Please try again.');
        }
        if (typeof body.session_token !== 'string' || !/^deriv_[A-Za-z0-9_-]{64}$/.test(body.session_token)) {
          throw Error('Invalid sign-in response.');
        }
        sessionStorage.setItem(SESSION_KEY, body.session_token);
        setToken(body.session_token);
        setSelectedId('');
        setError('');
        pushNotification('bot', 'Deriv Connected', 'Successfully authorized Deriv account session.');
        return;
      }
      throw Error('Sign-in timed out. Please try again.');
    } catch (e) {
      setError((e as Error).message);
    } finally {
      sessionStorage.removeItem(HANDOFF_KEY);
      if (!popup.closed) popup.close();
      setOauthBusy(false);
    }
  }

  useEffect(() => {
    if (!token || oauthBusy) return;
    let active = true;
    let inFlight = false;
    const controller = new AbortController();
    async function load() {
      if (inFlight) return;
      inFlight = true;
      setBusy(true);
      try {
        const response = await fetch(API + '/api/deriv/accounts', {
          cache: 'no-store',
          headers: { Authorization: 'Bearer ' + token },
          signal: controller.signal,
        });
        const body = await response.json();
        if (!active) return;
        if (response.status === 401) {
          sessionStorage.removeItem(SESSION_KEY);
          setToken('');
          setData(null);
          setError('Your PlayGo session expired. Please sign in again.');
          return;
        }
        if (!response.ok) {
          throw Error(typeof body.detail === 'string' ? body.detail : 'Unable to load Deriv balances.');
        }
        if (typeof body.connected !== 'boolean' || !Array.isArray(body.accounts)) {
          throw Error('Invalid balance response.');
        }
        setData(body as Snapshot);
        setError('');
      } catch (e) {
        if (active) {
          setData(null);
          setError(
            (e as Error).message === 'Failed to fetch'
              ? 'Cannot reach the balance service. Please retry.'
              : (e as Error).message
          );
        }
      } finally {
        inFlight = false;
        if (active) setBusy(false);
      }
    }
    void load();
    const timer = window.setInterval(() => void load(), 30000);
    return () => {
      active = false;
      controller.abort();
      window.clearInterval(timer);
    };
  }, [token, refresh, oauthBusy]);

  useEffect(() => {
    if (!token || !derivSession || selected?.account_type !== 'demo') {
      setBotState(null);
      setBotError('');
      return;
    }
    let active = true;
    setBotError('');
    fetch(API + '/api/deriv/demo-bot?account_id=' + encodeURIComponent(selected.account_id), {
      cache: 'no-store',
      headers: { Authorization: 'Bearer ' + token },
    })
      .then(async (response) => {
        const body = await response.json();
        if (!response.ok) {
          throw Error(typeof body.detail === 'string' ? body.detail : 'Unable to load demo bot status.');
        }
        return body as DemoBotState;
      })
      .then((state) => {
        if (active) setBotState(state);
      })
      .catch((e) => {
        if (active) {
          setBotState(null);
          setBotError((e as Error).message);
        }
      });
    return () => {
      active = false;
    };
  }, [token, derivSession, selected?.account_id, selected?.account_type, refresh]);

  async function botAction(action: 'start' | 'stop', config?: BotConfig) {
    if (!selected || selected.account_type !== 'demo') return;
    setBotBusy(true);
    setBotError('');
    try {
      const response = await fetch(API + '/api/deriv/demo-bot/' + action, {
        method: 'POST',
        headers: { Authorization: 'Bearer ' + token, 'Content-Type': 'application/json' },
        body: JSON.stringify({ account_id: selected.account_id, ...(config || {}) }),
      });
      const body = await response.json();
      if (typeof body.execution === 'string') setBotState(body as DemoBotState);
      if (!response.ok) {
        throw Error(
          typeof body.detail === 'string'
            ? body.detail
            : typeof body.last_error === 'string'
            ? body.last_error
            : 'Unable to ' + action + ' the demo bot.'
        );
      }

      if (action === 'start') {
        pushNotification(
          'bot',
          'BOT STARTED',
          `Demo bot initiated on ${config?.symbol || body.symbol || 'EUR/USD'} · Stake USD ${
            config?.stake || body.stake || '2.00'
          } · Cap USD ${config?.daily_stake_limit || body.daily_stake_limit || '5.00'}.`
        );
      } else {
        pushNotification(
          'bot',
          'BOT STOPPED',
          `Demo bot manually stopped on account ${selected.account_id}.`
        );
      }
    } catch (e) {
      const msg = (e as Error).message;
      setBotError(msg);
      pushNotification('risk', `Bot ${action.toUpperCase()} Alert`, msg);
    } finally {
      setBotBusy(false);
    }
  }

  async function resolveBot() {
    if (!selected || selected.account_type !== 'demo') return;
    setBotBusy(true);
    setBotError('');
    try {
      const response = await fetch(API + '/api/deriv/demo-bot/resolve', {
        method: 'POST',
        headers: { Authorization: 'Bearer ' + token, 'Content-Type': 'application/json' },
        body: JSON.stringify({ account_id: selected.account_id, confirmed_account_review: true }),
      });
      const body = await response.json();
      if (typeof body.execution === 'string') setBotState(body as DemoBotState);
      if (!response.ok) {
        throw Error(typeof body.detail === 'string' ? body.detail : 'Unable to resolve demo bot status.');
      }
      pushNotification('bot', 'Risk Alert Resolved', 'Demo account review acknowledged. Bot is ready.');
    } catch (e) {
      setBotError((e as Error).message);
    } finally {
      setBotBusy(false);
    }
  }

  useEffect(() => {
    if (!token || !derivSession || !selected || selected.account_type !== 'demo' ||
        !botState?.running || botState.account_id !== selected.account_id) return;
    const accountId = selected.account_id;
    let active = true;
    let inFlight = false;
    async function cycle() {
      if (inFlight) return;
      inFlight = true;
      try {
        const response = await fetch(API + '/api/deriv/demo-bot/cycle', {
          method: 'POST',
          headers: { Authorization: 'Bearer ' + token, 'Content-Type': 'application/json' },
          body: JSON.stringify({ account_id: accountId }),
        });
        const body = await response.json();
        if (active && typeof body.execution === 'string') setBotState(body as DemoBotState);
        if (response.status === 401) {
          sessionStorage.removeItem(SESSION_KEY);
          setToken('');
          setData(null);
          setError('Your Deriv session expired. Please sign in again.');
        }
        if (!response.ok) {
          throw Error(
            typeof body.last_error === 'string'
              ? body.last_error
              : typeof body.detail === 'string'
              ? body.detail
              : 'Demo bot cycle failed.'
          );
        }
        if (active) setBotError('');
      } catch (e) {
        if (active) setBotError((e as Error).message);
      } finally {
        inFlight = false;
      }
    }
    void cycle();
    const timer = window.setInterval(() => void cycle(), 30000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [token, derivSession, selected?.account_id, selected?.account_type, botState?.running, botState?.account_id]);

  async function login(e: React.FormEvent) {
    e.preventDefault();
    setSigningIn(true);
    setError('');
    try {
      const r = await fetch(API + '/api/identity/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      });
      const body = await r.json();
      if (!r.ok) throw Error(typeof body.detail === 'string' ? body.detail : 'Sign-in failed.');
      if (typeof body.access_token !== 'string') throw Error('Invalid sign-in response.');
      sessionStorage.setItem(SESSION_KEY, body.access_token);
      setToken(body.access_token);
      setPassword('');
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSigningIn(false);
    }
  }

  async function logout() {
    setOauthBusy(false);
    setBusy(true);
    setError('');
    try {
      const r = await fetch(API + (derivSession ? '/api/deriv/session/logout' : '/api/identity/logout'), {
        method: 'POST',
        headers: { Authorization: 'Bearer ' + token },
      });
      if (!r.ok && r.status !== 401) throw Error('Unable to revoke the session. Please retry sign-out.');
      sessionStorage.removeItem(SESSION_KEY);
      setToken('');
      setData(null);
      setPassword('');
      pushNotification('bot', 'Signed Out', 'Your PlayGo session ended safely.');
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  function showDashboardPage(page: DashboardPage) {
    setDashboardPage(page);
    if (window.location.pathname !== DASHBOARD_PATHS[page]) {
      window.history.pushState(null, '', DASHBOARD_PATHS[page]);
    }
    window.scrollTo({ top: 0, behavior: 'auto' });
  }

  return (
        <main className="realWorkspace">
      {liveToast && (
        <div className={`liveAlertToast toast-${liveToast.category}`} role="status" aria-live="polite">
          <div>
            <b>
              {liveToast.title} {liveToast.amountLabel ? `(${liveToast.amountLabel})` : ''}
            </b>
            <p>{liveToast.message}</p>
          </div>
          <button type="button" aria-label="Dismiss alert" onClick={() => setLiveToast(null)}>
            ×
          </button>
        </div>
      )}
      <header>
        <div className="realBrand">
          <Activity size={25} />
          <div>
            <b>
              PlayGo<span>.</span>
            </b>
            <small>DERIV ACCOUNT OVERVIEW</small>
          </div>
        </div>
        <div className="realHeaderActions">
          <span className={`realBadge ${selected?.account_type === 'demo' ? 'demoBadge' : ''}`}>
            <ShieldCheck size={13} />
            {selected ? selected.account_type.toUpperCase() + ' ACCOUNT' : 'READ ONLY'}
          </span>
          <NotificationPanel
            logs={notifications}
            onMarkAllRead={markAllRead}
            onClearAll={clearAllNotifications}
          />
          {token && (
            <button disabled={busy} onClick={() => void logout()}>
              <LogOut size={15} /> Sign out
            </button>
          )}
        </div>
        <Navbar currentPage={dashboardPage} onNavigate={showDashboardPage} />
      </header>

      {(dashboardPage === 'trade-bot' || dashboardPage === 'pnl-hedge') && data?.connected && selected && (
        <div className="accountMarketControls dashboardAccountControl">
          <label>
            Deriv account
            <select value={selected.account_id} onChange={(event) => setSelectedId(event.target.value)}>
              {data.accounts.map((account) => (
                <option key={account.account_id} value={account.account_id}>
                  {account.account_type === 'demo' ? 'Demo' : 'Real'} · {account.account_id} · {account.currency}
                </option>
              ))}
            </select>
          </label>
        </div>
      )}

      {dashboardPage === 'account' && (
        <AccountPage
          token={token}
          oauthBusy={oauthBusy}
          busy={busy}
          signingIn={signingIn}
          data={data}
          selected={selected}
          selectedId={selectedId}
          error={error}
          username={username}
          password={password}
          onSelectId={setSelectedId}
          onRefresh={() => setRefresh((v) => v + 1)}
          onSignInDeriv={() => void signInWithDeriv()}
          onOwnerLogin={login}
          onUsernameChange={setUsername}
          onPasswordChange={setPassword}
        />
      )}

      {dashboardPage === 'market' && <MarketPage load={loadMarkets} />}

      {dashboardPage === 'trade-bot' && (
        <TradeBotPage
          derivSession={derivSession}
          selected={selected}
          botState={botState?.account_id === selected?.account_id ? botState : null}
          botBusy={botBusy}
          botError={botError}
          oauthBusy={oauthBusy}
          onBotAction={(action, config) => void botAction(action, config)}
          onResolveBot={() => void resolveBot()}
          onSignInDeriv={() => void signInWithDeriv()}
          results={derivSession && selected?.account_type === 'demo' && (
            <DerivMarketPanel
              key={selected.account_id}
              view="performance"
              load={loadMarkets}
              accountId={selected.account_id}
              accountType="demo"
              accountBalance={selected.balance}
              activeContractId={botState?.active_contract_id}
              botOnly
            />
          )}
        />
      )}

      {dashboardPage === 'pnl-hedge' && <PnlHedgePage load={loadMarkets} data={data} selected={selected} />}

      <footer>
        <span>PlayGo / Deriv account overview</span>
      </footer>
    </main>
  );
}
