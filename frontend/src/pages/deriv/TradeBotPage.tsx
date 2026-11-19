import React, { useEffect, useState } from 'react';
import { SlidersHorizontal, Play, Square, RotateCcw, Clock } from 'lucide-react';
import { Account, BotConfig, DemoBotState } from '../../types/trading';

type Props = {
  derivSession: boolean;
  selected: Account | undefined;
  botState: DemoBotState | null;
  selectedStrategyName: string;
  botBusy: boolean;
  botError: string;
  oauthBusy: boolean;
  results?: React.ReactNode;
  onBotAction: (action: 'start' | 'stop', config?: BotConfig) => void;
  onResolveBot: () => void;
  onSignInDeriv: () => void;
};

const PAIRS = [
  { value: 'frxEURUSD', label: 'EUR/USD' },
  { value: 'frxGBPUSD', label: 'GBP/USD' },
  { value: 'frxUSDJPY', label: 'USD/JPY' },
  { value: 'frxAUDUSD', label: 'AUD/USD' },
  { value: 'frxUSDCAD', label: 'USD/CAD' },
  { value: 'frxEURGBP', label: 'EUR/GBP' },
  { value: 'R_10', label: 'Volatility 10 Index' },
  { value: 'R_25', label: 'Volatility 25 Index' },
  { value: 'R_50', label: 'Volatility 50 Index' },
  { value: 'R_75', label: 'Volatility 75 Index' },
  { value: 'R_100', label: 'Volatility 100 Index' },
];

export default function TradeBotPage({
  derivSession,
  selected,
  botState,
  selectedStrategyName,
  botBusy,
  botError,
  oauthBusy,
  results,
  onBotAction,
  onResolveBot,
  onSignInDeriv,
}: Props) {
  const [configuring, setConfiguring] = useState(false);
  const [symbol, setSymbol] = useState('frxEURUSD');
  const [contractType, setContractType] = useState<'CALL_PUT' | 'CALL' | 'PUT'>('CALL_PUT');
  const [duration, setDuration] = useState(5);
  const [stake, setStake] = useState('2.00');
  const [dailyLimit, setDailyLimit] = useState('5.00');
  const [secondsLeft, setSecondsLeft] = useState<number | null>(null);

  useEffect(() => {
    if (botState) {
      if (botState.symbol) setSymbol(botState.symbol);
      if (botState.duration_minutes) setDuration(botState.duration_minutes);
      if (botState.stake) setStake(Number(botState.stake).toFixed(2));
      if (botState.daily_stake_limit) setDailyLimit(Number(botState.daily_stake_limit).toFixed(2));
    }
  }, [botState?.symbol, botState?.duration_minutes, botState?.stake, botState?.daily_stake_limit]);

  // Live countdown timer for active contract
  useEffect(() => {
    if (!botState?.active_contract_id || !botState.last_trade?.created_at) {
      setSecondsLeft(null);
      return;
    }
    const createdMs = Date.parse(botState.last_trade.created_at);
    const durationMs = (botState.duration_minutes || 5) * 60 * 1000;
    if (!Number.isFinite(createdMs)) {
      setSecondsLeft(null);
      return;
    }

    const updateTimer = () => {
      const remaining = Math.max(0, Math.ceil((createdMs + durationMs - Date.now()) / 1000));
      setSecondsLeft(remaining);
    };
    updateTimer();
    const interval = window.setInterval(updateTimer, 1000);
    return () => window.clearInterval(interval);
  }, [botState?.active_contract_id, botState?.last_trade?.created_at, botState?.duration_minutes]);

  const activePairLabel =
    PAIRS.find((p) => p.value === (botState?.symbol || symbol))?.label || botState?.symbol || 'EUR/USD';
  const activeDuration = botState?.duration_minutes ?? duration;
  const activeStake = Number(botState?.stake ?? stake).toFixed(2);
  const activeLimit = Number(botState?.daily_stake_limit ?? dailyLimit).toFixed(2);

  function formatCountdown(secs: number) {
    const mins = Math.floor(secs / 60);
    const rem = secs % 60;
    return `${String(mins).padStart(2, '0')}:${String(rem).padStart(2, '0')}`;
  }

  function handleStartWithSetup(e: React.FormEvent) {
    e.preventDefault();
    onBotAction('start', {
      symbol,
      contract_type: contractType,
      duration_minutes: duration,
      stake: Number(stake).toFixed(2),
      daily_stake_limit: Number(dailyLimit).toFixed(2),
    });
    setConfiguring(false);
  }

  return (
    <div className="independentPage">
      {derivSession && selected?.account_type === 'demo' ? (
        <section className="demoBotPanel" aria-label="Deriv demo bot">
          <div className="demoBotHeading">
            <div>
              <h2>Deriv demo bot</h2>
              <p>
                {selectedStrategyName} · {activePairLabel} · {activeDuration}-minute Rise/Fall
              </p>
            </div>
            <div className="botHeaderBadges">
              {!botState?.running && (
                <button
                  type="button"
                  className="botConfigToggle"
                  onClick={() => setConfiguring((prev) => !prev)}
                  disabled={botBusy}
                >
                  <SlidersHorizontal size={14} />
                  {configuring ? 'Close setup' : 'New setup / Configure'}
                </button>
              )}
              <span className={botState?.running ? 'botRunning' : 'botStopped'}>
                {botState?.status?.replace(/_/g, ' ') || 'checking'}
              </span>
            </div>
          </div>

          {botState?.active_contract_id && (
            <div className="activeContractBanner" role="status">
              <div className="activeContractInfo">
                <span className="pulseDot" />
                <div>
                  <b>Live Contract Open · #{botState.active_contract_id}</b>
                  <small>
                    {botState.last_trade?.side === 'BUY' ? 'Rise (CALL)' : 'Fall (PUT)'} · Stake USD{' '}
                    {botState.last_trade?.stake || activeStake}
                  </small>
                </div>
              </div>
              <div className="activeContractTimer">
                <Clock size={15} />
                <strong>{secondsLeft !== null ? formatCountdown(secondsLeft) : 'In progress'}</strong>
              </div>
            </div>
          )}

          {configuring && !botState?.running && (
            <form className="botSetupForm" onSubmit={handleStartWithSetup}>
              <div className="botSetupHeader">
                <b>Configure New Bot Setup</b>
                <small>Adjust parameters before initiating automated execution</small>
              </div>
              <div className="botSetupGrid">
                <label>
                  Market Pair
                  <select value={symbol} onChange={(e) => setSymbol(e.target.value)}>
                    {PAIRS.map((p) => (
                      <option key={p.value} value={p.value}>
                        {p.label}
                      </option>
                    ))}
                  </select>
                </label>

                <label>
                  Direction Mode
                  <select
                    value={contractType}
                    onChange={(e) => setContractType(e.target.value as 'CALL_PUT' | 'CALL' | 'PUT')}
                  >
                    <option value="CALL_PUT">Both (Rise &amp; Fall via EMA)</option>
                    <option value="CALL">Rise Only (CALL)</option>
                    <option value="PUT">Fall Only (PUT)</option>
                  </select>
                </label>

                <label>
                  Contract Duration
                  <select value={duration} onChange={(e) => setDuration(Number(e.target.value))}>
                    <option value={1}>1 Minute</option>
                    <option value={5}>5 Minutes</option>
                    <option value={15}>15 Minutes</option>
                    <option value={30}>30 Minutes</option>
                    <option value={60}>1 Hour</option>
                  </select>
                </label>

                <label>
                  Stake per Contract (USD)
                  <input
                    type="number"
                    min="0.35"
                    max="100"
                    step="0.05"
                    required
                    value={stake}
                    onChange={(e) => setStake(e.target.value)}
                  />
                </label>

                <label>
                  Daily Stake Cap (USD)
                  <input
                    type="number"
                    min="1"
                    max="500"
                    step="0.50"
                    required
                    value={dailyLimit}
                    onChange={(e) => setDailyLimit(e.target.value)}
                  />
                </label>
              </div>

              <div className="botSetupFooter">
                <button
                  type="button"
                  onClick={() => {
                    setSymbol('frxEURUSD');
                    setContractType('CALL_PUT');
                    setDuration(5);
                    setStake('2.00');
                    setDailyLimit('5.00');
                  }}
                >
                  <RotateCcw size={14} /> Reset defaults
                </button>
                <button type="submit" className="realPrimary" disabled={botBusy}>
                  <Play size={14} /> Save &amp; Initiate Bot
                </button>
              </div>
            </form>
          )}

          <div className="demoBotLimits">
            <span>
              Stake per contract <b>USD {activeStake}</b>
            </span>
            <span>
              Daily stake cap <b>USD {activeLimit}</b>
            </span>
            <span>
              Used today <b>USD {Number(botState?.daily_stake || 0).toFixed(2)}</b>
            </span>
          </div>

          {botState?.last_trade && !botState.active_contract_id && (
            <small className="demoBotTrade">
              Last contract: {botState.last_trade.side === 'BUY' ? 'Rise' : 'Fall'} · {botState.last_trade.contract_id} ·{' '}
              {botState.last_trade.status}
            </small>
          )}

          {results}
          <section className="accountPerformanceSection" aria-labelledby="trade-activity-heading">
            <h3 id="trade-activity-heading">Logs &amp; trade activity</h3>
            <p role="status">{botState?.running ? 'Bot running' : 'Bot paused'}
              {botState?.last_cycle_at ? ` · Last check ${new Date(botState.last_cycle_at).toLocaleString()}` : ''}
              {' · '}Deriv demo balance {selected.balance === null ? 'unavailable' : `${selected.currency} ${selected.balance}`}
            </p>
            {botState?.trade_activity?.length ? (
              <div className="accountMarketTableWrap accountRecentActivities">
                <table className="accountMarketTable">
                  <thead><tr><th>Event time</th><th>Initiated</th><th>Market</th><th>Direction</th><th>Stake</th><th>Activity</th><th>Contract ID</th></tr></thead>
                  <tbody>{[...botState.trade_activity].reverse().map((event, index) => (
                    <tr key={`${event.time}-${index}`}>
                      <td><time dateTime={event.time}>{new Date(event.time).toLocaleString()}</time></td>
                      <td><time dateTime={event.initiated_at}>{new Date(event.initiated_at).toLocaleString()}</time></td>
                      <td>{event.symbol}</td><td>{event.side === 'BUY' ? 'Rise' : 'Fall'}</td>
                      <td>{selected.currency} {Number(event.stake).toFixed(2)}</td><td>{event.status}</td>
                      <td>{event.contract_id ?? '—'}</td>
                    </tr>
                  ))}</tbody>
                </table>
              </div>
            ) : <p className="accountMarketMessage">No trade events have been recorded for this demo account yet.</p>}
          </section>

          {botState?.last_error && (
            <p className="realError" role="alert">
              {botState.last_error}
            </p>
          )}
          {botError && (
            <p className="realError" role="alert">
              {botError}
            </p>
          )}

          {botState?.status === 'needs_review' && (
            <p className="demoBotWarning" role="alert">
              The outcome of a trade request is uncertain. Check your Deriv demo account before attempting another
              start.
            </p>
          )}

          {!configuring && (
            <div className="demoBotActions">
              {botState?.status === 'needs_review' ? (
                <button className="botStopButton" disabled={botBusy} onClick={onResolveBot}>
                  {botBusy ? 'Resolving...' : 'I checked Deriv — acknowledge'}
                </button>
              ) : botState?.running ? (
                <button className="botStopButton" disabled={botBusy} onClick={() => onBotAction('stop')}>
                  <Square size={14} /> {botBusy ? 'Stopping...' : 'Stop bot'}
                </button>
              ) : (
                <button
                  className="realPrimary"
                  disabled={botBusy || !botState}
                  onClick={() => onBotAction('start')}
                >
                  <Play size={14} /> {botBusy ? 'Starting...' : 'Initiate demo bot'}
                </button>
              )}
            </div>
          )}

          {!botState && <small role="status">Loading bot status...</small>}
        </section>
      ) : (
        <section className="demoBotPanel">
          <div className="demoBotHeading">
            <div>
              <h2>Trading Bot</h2>
              <p>Demo-only execution</p>
            </div>
          </div>
          <p className="demoBotCopy">
            {!derivSession
              ? 'Sign in with Deriv to access the demo bot.'
              : selected?.account_type === 'real'
              ? 'Select a demo account to access the demo bot. Real-account trading is disabled.'
              : 'Select a verified demo account to access the demo bot.'}
          </p>
          <p className="demoBotCopy">Selected agent strategy: {selectedStrategyName}.</p>
          {!derivSession && (
            <button className="realPrimary" disabled={oauthBusy} onClick={onSignInDeriv}>
              {oauthBusy ? 'Connecting...' : 'Sign in with Deriv'}
            </button>
          )}
        </section>
      )}
    </div>
  );
}
