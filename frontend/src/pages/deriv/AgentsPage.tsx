import React, { useEffect, useMemo, useState } from 'react';
import '../../styles/agents.css';
import { AGENT_PROMPT } from '../../data/agentPrompt';
import { Account, DemoBotState, Snapshot } from '../../types/trading';

type Props = {
  load: (path: string) => Promise<unknown>;
  data: Snapshot | null;
  selected: Account | undefined;
  botState: DemoBotState | null;
};

type Performance = {
  source: string;
  account_id: string;
  currency: string;
  recent_closed: { contract_id: string; profit: string }[];
  bot_contract_ids?: string[];
  unresolved_bot_contract_ids?: string[];
  history_available?: boolean;
  realized_may_be_truncated?: boolean;
  bot_tracking_unavailable?: boolean;
};

const phases = [
  ['A. Paper foundation', 'Immutable audit ledger, authorization and isolation, atomic writes, walk-forward and out-of-sample validation, deterministic replay, and 30+ clean reconciliation days.'],
  ['B. Demo adapter', 'Idempotency, order lifecycle, cycle and daily reconciliation, chaos tests, 60–90 days of demo evidence, and proven kill switches.'],
  ['C. Legal review and authorization', 'Jurisdiction review, written strategy specification, and signed Live Authorization.'],
  ['D. Controlled pilot', 'Authorized minimal capital and daily human review for 2–4 weeks.'],
  ['E. Governance', 'Weekly, monthly, and quarterly reviews, with written capital decisions.'],
];

// Lower bound of the 95% Wilson interval for a win rate.
function wilsonLower(wins: number, n: number): number {
  if (n === 0) return 0;
  const z = 1.96, p = wins / n, z2 = z * z;
  return (p + z2 / (2 * n) - z * Math.sqrt((p * (1 - p) + z2 / (4 * n)) / n)) / (1 + z2 / n);
}

const pct = (v: number) => (v * 100).toFixed(1) + '%';
const num = (v: unknown) => { const x = Number(v); return Number.isFinite(x) ? x : 0; };

export default function AgentsPage({ load, data, selected, botState }: Props) {
  const [perf, setPerf] = useState<Performance | null>(null);
  const [error, setError] = useState('');
  const [copied, setCopied] = useState(false);
  const accountId = data?.connected ? selected?.account_id : undefined;

  useEffect(() => {
    if (!accountId) { setPerf(null); return; }
    let active = true, inFlight = false;
    const poll = async () => {
      if (inFlight) return;
      inFlight = true;
      try {
        const body = await load(`/api/deriv/accounts/${encodeURIComponent(accountId)}/performance`);
        const result = body as Performance;
        if (result.source !== 'DERIV' || result.account_id !== accountId || !Array.isArray(result.recent_closed)) {
          throw new Error('Deriv returned invalid performance data.');
        }
        if (active) { setPerf(result); setError(''); }
      } catch (e) {
        if (active) setError(e instanceof Error ? e.message : 'Unable to load performance.');
      } finally { inFlight = false; }
    };
    void poll();
    const timer = window.setInterval(poll, 30_000);
    return () => { active = false; window.clearInterval(timer); };
  }, [accountId, load]);

  async function copyPrompt() {
    try {
      await navigator.clipboard.writeText(AGENT_PROMPT);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch { setCopied(false); }
  }

  const stats = useMemo(() => {
    const snapshot = perf?.account_id === accountId ? perf : null;
    const ids = new Set(snapshot?.bot_contract_ids ?? []);
    const observed = new Map<string, number>();
    for (const trade of snapshot?.recent_closed ?? []) {
      const profit = Number(trade.profit);
      if (ids.has(trade.contract_id) && typeof trade.profit === 'string' && trade.profit.trim() && Number.isFinite(profit)) {
        observed.set(trade.contract_id, profit);
      }
    }
    const results = [...observed.values()];
    const wins = results.filter((profit) => profit > 0).length;
    return {
      n: results.length,
      wins,
      net: results.reduce((total, profit) => total + profit, 0),
      incomplete: snapshot?.history_available === false || snapshot?.realized_may_be_truncated ||
        snapshot?.bot_tracking_unavailable || !!snapshot?.unresolved_bot_contract_ids?.length,
    };
  }, [accountId, perf]);
  const used = num(botState?.daily_stake), limit = num(botState?.daily_stake_limit);
  const budget = limit > 0 ? Math.min(100, (used / limit) * 100) : 0;

  const agents = [
    { name: 'Research', badge: 'Partial', tone: 'partial', note: 'Offline breakout backtest only. No live research feed or news.',
      metric: 'Mode: offline' },
    { name: 'Strategy & Trade', badge: 'Live (demo)', tone: 'live', note: 'EMA crossover signal. Not validated as profitable.',
      metric: botState ? `${botState.symbol} · ${botState.contract_type} · ${botState.duration_minutes}m` : 'Bot not loaded' },
    { name: 'Risk', badge: 'Partial', tone: 'partial', note: 'Stake cap and daily stake limit. Loss-based auto-stop not built yet.',
      metric: botState ? `Budget ${used.toFixed(2)} / ${limit.toFixed(2)}` : 'n/a' },
    { name: 'Investments', badge: 'Partial', tone: 'partial', note: 'Demo balance and stake sizing only. No portfolio allocation logic.',
      metric: selected ? `Balance ${selected.balance ?? 'n/a'} ${selected.currency}` : 'n/a' },
    { name: 'Accounting & Finance', badge: 'Live', tone: 'live', note: 'Settlement reconciliation and realized/unrealized P&L.',
      metric: stats.n ? `Observed bot P&L ${perf?.currency} ${stats.net.toFixed(2)}` : 'No confirmed bot settlements' },
    { name: 'Supervisor', badge: 'Partial', tone: 'partial', note: 'Tracks bot status and errors. No external watchdog or alerts.',
      metric: botState ? (botState.last_error ? 'Error: ' + botState.last_error : 'Status: ' + botState.status) : 'n/a' },
  ];

  const activity = [...(botState?.trade_activity ?? [])].reverse();

  return (
    <div className="independentPage agentsPage">
      <section className="agentsBanner">
        <strong>Real-money routing locked</strong><span>Paper and demo operations only. This page reports activity and evidence requirements.</span>
      </section>



      <section className="agentsGrid">
        {agents.map((a) => (
          <article key={a.name} className="agentCard">
            <header><h3>{a.name}</h3><span className={'agentBadge agentBadge-' + a.tone}>{a.badge}</span></header>
            <p>{a.note}</p>
            <div className="agentMetric">{a.metric}</div>
            {a.name === 'Risk' && (
              <div className="agentBar" role="progressbar" aria-valuenow={Math.round(budget)} aria-valuemin={0} aria-valuemax={100}>
                <i style={{ width: budget + '%' }} />
              </div>
            )}
          </article>
        ))}
      </section>

      <section className="agentsPanel">
        <h2>Trade activity</h2>
        {activity.length === 0 ? <p className="agentsHint">No bot trades yet.</p> : (
          <ul className="agentFeed">
            {activity.slice(0, 12).map((t, i) => (
              <li key={(t.contract_id ?? t.initiated_at) + String(i)} className="agentFeedItem">
                <span className={'agentSide ' + (t.side === 'BUY' ? 'up' : 'down')}>{t.side === 'BUY' ? 'CALL' : 'PUT'}</span>
                <span>{t.symbol}</span><span>stake {t.stake}</span>
                <span className="agentStatus">{t.status}</span><time>{t.time}</time>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="agentsPanel">
        <h2>AI operating prompt <small>paste into any AI assistant</small></h2>
        <button type="button" className="agentCopy" onClick={() => void copyPrompt()}>{copied ? 'Copied' : 'Copy prompt'}</button>
        <details>
          <summary>Show prompt</summary>
          <pre className="agentPrompt">{AGENT_PROMPT}</pre>
        </details>
      </section>

      <section className="agentsPanel">
        <h2>Observed demo results</h2>
        {error && <p className="agentsError" role="alert">{error}{perf ? ' Showing the last successful snapshot.' : ''}</p>}
        {selected?.account_type !== 'demo' ? <p>Select a signed-in demo account.</p> :
          !perf ? <p role="status">{error ? 'Results unavailable.' : 'Loading Deriv results…'}</p> :
          <p>{stats.n} confirmed bot settlements · Win rate {stats.n ? pct(stats.wins / stats.n) : '—'} · 95% Wilson lower bound {stats.n ? pct(wilsonLower(stats.wins, stats.n)) : '—'}</p>}
        {stats.incomplete && <p className="agentsHint">Deriv history or contract coverage is incomplete.</p>}
        <p className="agentsHint">Account observations do not establish an eligible research sample. The 85% win-rate target is a research hypothesis.</p>
      </section>
      <section className="agentsPanel">
        <h2>Required evidence in phase order</h2>
        <ol className="agentGates">{phases.map(([name, evidence], index) => (
          <li key={name}><strong>{name} · {index === 0 ? 'Evidence pending' : 'Blocked by prior phase'}</strong><small>{evidence}</small></li>
        ))}</ol>
        <p className="agentsHint">Research evidence requires 300 eligible settled trades, a Wilson lower bound above cost-adjusted break-even, positive net expectancy, and authorized drawdown limits across both sample halves.</p>
      </section>
    </div>
  );
}
