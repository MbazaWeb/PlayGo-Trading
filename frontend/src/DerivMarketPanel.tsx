import { useEffect, useMemo, useState } from 'react';

type Candle = {
  epoch: number;
  open: string;
  high: string;
  low: string;
  close: string;
};

type Market = {
  symbol: string;
  pair: string;
  display_name: string;
  pip_size: string;
  exchange_is_open: boolean;
  is_trading_suspended: boolean;
};

type Tick = {
  quote: number;
  bid: number | null;
  ask: number | null;
  epoch: number;
};

type Position = {
  contract_id: string;
  symbol: string;
  contract_type: string;
  direction: 'up' | 'down' | 'other';
  buy_price: string;
  profit: string;
  purchase_time: number | string | null;
};

type Exposure = {
  symbol: string;
  up_stake: string;
  down_stake: string;
  other_stake: string;
  up_count: number;
  down_count: number;
  other_count: number;
  opposing_stake: string;
};

type ClosedPosition = {
  contract_id: string;
  symbol: string;
  contract_type: string;
  buy_price: string;
  sell_price: string;
  profit: string;
  sell_time: number | string | null;
};

type AccountActivity = {
  id: string;
  contractId: string;
  symbol: string;
  contract_type: string;
  label: 'Open · current P&L' | 'Closed · realized P&L';
  time: number | string;
  profit: string;
};

type Performance = {
  source: 'DERIV';
  execution: 'DISABLED';
  account_id: string;
  account_type: 'demo' | 'real';
  currency: string;
  open_positions: Position[];
  unrealized_pnl: string;
  realized_pnl: string;
  realized_transaction_count: number;
  realized_window: string;
  realized_may_be_truncated: boolean;
  recent_closed: ClosedPosition[];
  opposing_exposure: Exposure[];
  exposure_note: string;
  observed_at: string;
  bot_contract_ids: string[];
  unresolved_bot_contract_ids: string[];
  bot_tracking_unavailable: boolean;
};

type Props = {
  load: (path: string) => Promise<unknown>;
  view: 'markets' | 'performance';
  accountId?: string;
  accountType?: 'demo' | 'real';
  accountBalance?: string | null;
  botOnly?: boolean;
  activeContractId?: string | null;
};

const INTERVALS = [
  { seconds: '60', label: '1 minute' },
  { seconds: '120', label: '2 minutes' },
  { seconds: '180', label: '3 minutes' },
  { seconds: '300', label: '5 minutes' },
  { seconds: '600', label: '10 minutes' },
  { seconds: '900', label: '15 minutes' },
  { seconds: '1800', label: '30 minutes' },
  { seconds: '3600', label: '1 hour' },
  { seconds: '7200', label: '2 hours' },
  { seconds: '14400', label: '4 hours' },
  { seconds: '28800', label: '8 hours' },
  { seconds: '86400', label: '1 day' },
];

function marketStatus(market: Market) {
  return market.is_trading_suspended ? 'Suspended' : market.exchange_is_open ? 'Open' : 'Closed';
}

function ema(values: number[], period: number) {
  if (!values.length) return [];
  const multiplier = 2 / (period + 1);
  return values.reduce<number[]>((series, value) => {
    const previous = series[series.length - 1];
    series.push(previous === undefined ? value : value * multiplier + previous * (1 - multiplier));
    return series;
  }, []);
}

function amount(value: string | null | undefined, currency: string, signed = false) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) {
    return 'Unavailable';
  }
  const number = Number(value);
  const sign = signed && number > 0 ? '+' : '';
  return `${sign}${currency} ${number.toLocaleString('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 8,
  })}`;
}

function formatTime(value: number | string) {
  const numeric = typeof value === 'number' || /^\d+$/.test(value) ? Number(value) * 1000 : Date.parse(value);
  return Number.isFinite(numeric) ? new Date(numeric).toLocaleString() : 'Unavailable';
}

function timestamp(value: number | string) {
  const parsed = typeof value === 'number' || /^\d+$/.test(value) ? Number(value) * 1000 : Date.parse(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function decimalPlaces(pipSize: string) {
  const places = pipSize.split('.')[1]?.length ?? 0;
  return Math.min(places, 8);
}

export default function DerivMarketPanel({
  load, view, accountId, accountType, accountBalance, botOnly = false, activeContractId,
}: Props) {
  const [markets, setMarkets] = useState<Market[]>([]);
  const [pair, setPair] = useState('');
  const [interval, setInterval] = useState('300');
  const [candles, setCandles] = useState<Candle[]>([]);
  const [ticks, setTicks] = useState<Record<string, Tick>>({});
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('All');
  const [feedState, setFeedState] = useState('Loading market catalog...');
  const [catalogError, setCatalogError] = useState('');
  const [chartError, setChartError] = useState('');
  const [performance, setPerformance] = useState<Performance | null>(null);
  const [performanceError, setPerformanceError] = useState('');
  const [chartBusy, setChartBusy] = useState(false);
  const [performanceBusy, setPerformanceBusy] = useState(false);

  const selectedMarket = markets.find((market) => market.pair === pair);
  const visibleMarkets = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return markets.filter((market) =>
      (status === 'All' || marketStatus(market) === status)
      && (market.pair.toLowerCase().includes(needle) || market.display_name.toLowerCase().includes(needle)));
  }, [markets, search, status]);

  useEffect(() => {
    if (view !== 'markets') return undefined;
    let active = true;
    setCatalogError('');
    setFeedState('Loading market catalog...');
    const refreshCatalog = () => void load('/api/market/forex')
      .then((value) => {
        const result = value as { markets?: Market[] };
        if (
          !Array.isArray(result.markets)
          || !result.markets.length
        ) {
          throw new Error('Deriv returned an invalid Forex market catalog.');
        }
        const valid = result.markets.every((market) =>
          typeof market.symbol === 'string'
          && /^frx[A-Z]{6}$/.test(market.symbol)
          && market.pair === market.symbol.slice(3)
          && typeof market.display_name === 'string'
          && typeof market.pip_size === 'string'
          && typeof market.exchange_is_open === 'boolean'
          && typeof market.is_trading_suspended === 'boolean');
        if (!valid) throw new Error('Deriv returned invalid Forex market details.');
        if (active) {
          const updated = result.markets;
          setMarkets((current) => JSON.stringify(current) === JSON.stringify(updated) ? current : updated);
          setCatalogError('');
          setPair((current) =>
            result.markets?.some((market) => market.pair === current)
              ? current
              : result.markets?.[0]?.pair ?? '');
        }
      })
      .catch((reason: unknown) => {
        if (active) {
          setCatalogError(reason instanceof Error ? reason.message : 'Unable to load Forex markets.');
          setFeedState('Market catalog unavailable');
        }
      });
    refreshCatalog();
    const timer = window.setInterval(refreshCatalog, 60_000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [load, view]);

  useEffect(() => {
    if (view !== 'markets' || !markets.length) return undefined;
    let stopped = false;
    let retryTimer = 0;
    let frame = 0;
    let retries = 0;
    let socket: WebSocket | undefined;
    let pending: Record<string, Tick> = {};

    const connect = () => {
      if (stopped) return;
      setFeedState('Connecting to live prices...');
      socket = new WebSocket('wss://api.derivws.com/trading/v1/options/ws/public');
      socket.onopen = () => {
        retries = 0;
        setFeedState('Live prices connected');
        socket?.send(JSON.stringify({
          ticks: markets.map((market) => market.symbol),
          subscribe: 1,
        }));
      };
      socket.onmessage = (event) => {
        let message: { tick?: Record<string, unknown>; error?: { message?: string } };
        try {
          message = JSON.parse(String(event.data)) as { tick?: Record<string, unknown>; error?: { message?: string } };
        } catch {
          setFeedState('Live feed returned invalid data');
          return;
        }
        if (message.error) {
          setFeedState(message.error.message || 'Deriv rejected the live price subscription');
          return;
        }
        const tick = message.tick;
        if (!tick || typeof tick.symbol !== 'string') return;
        const knownMarket = markets.some((market) => market.symbol === tick.symbol);
        const quote = Number(tick.quote);
        const epoch = Number(tick.epoch);
        if (!knownMarket || !Number.isFinite(quote) || quote <= 0 || !Number.isFinite(epoch) || epoch <= 0) {
          return;
        }
        const bid = Number(tick.bid);
        const ask = Number(tick.ask);
        pending[tick.symbol] = {
          quote,
          bid: Number.isFinite(bid) && bid > 0 ? bid : null,
          ask: Number.isFinite(ask) && ask > 0 ? ask : null,
          epoch,
        };
        if (!frame) {
          frame = window.requestAnimationFrame(() => {
            setTicks((current) => ({ ...current, ...pending }));
            pending = {};
            frame = 0;
          });
        }
      };
      socket.onerror = () => setFeedState('Live price connection interrupted');
      socket.onclose = () => {
        if (stopped) return;
        setFeedState('Reconnecting to live prices...');
        retries += 1;
        retryTimer = window.setTimeout(connect, Math.min(15000, 1000 * 2 ** Math.min(retries, 4)));
      };
    };

    connect();
    return () => {
      stopped = true;
      window.clearTimeout(retryTimer);
      if (frame) window.cancelAnimationFrame(frame);
      socket?.close();
    };
  }, [markets, view]);

  useEffect(() => {
    if (view !== 'markets' || !pair) return undefined;
    let active = true;
    let firstLoad = true;
    setChartError('');
    setCandles([]);
    const fetchHistory = async () => {
      if (firstLoad) setChartBusy(true);
      try {
        const result = await load(
          `/api/market/candles?pair=${encodeURIComponent(pair)}&granularity=${interval}&count=80`,
        ) as { candles?: Candle[] };
        if (!Array.isArray(result.candles) || !result.candles.length) {
          throw new Error('No candle history is available for this market.');
        }
        if (active) setCandles(result.candles);
      } catch (reason) {
        if (active) {
          setChartError(reason instanceof Error ? reason.message : 'Unable to load candle history.');
        }
      } finally {
        if (active && firstLoad) setChartBusy(false);
        firstLoad = false;
      }
    };
    void fetchHistory();
    const timer = window.setInterval(() => void fetchHistory(), 60_000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [pair, interval, load, view]);

  useEffect(() => {
    if (view !== 'performance' || !accountId) {
      setPerformance(null);
      setPerformanceError('');
      setPerformanceBusy(false);
      return undefined;
    }
    const selectedAccountId = accountId;
    let active = true;
    let inFlight = false;
    const fetchPerformance = async () => {
      if (inFlight) return;
      inFlight = true;
      setPerformanceBusy(true);
      try {
        const result = await load(
          `/api/deriv/accounts/${encodeURIComponent(selectedAccountId)}/performance`,
        ) as Performance;
        if (
          result.source !== 'DERIV'
          || result.execution !== 'DISABLED'
          || result.account_id !== selectedAccountId
          || (accountType && result.account_type !== accountType)
          || !Array.isArray(result.open_positions)
          || !Array.isArray(result.opposing_exposure)
          || !Array.isArray(result.recent_closed)
        ) {
          throw new Error('Deriv returned invalid account performance data.');
        }
        if (active) {
          setPerformance(result);
          setPerformanceError('');
        }
      } catch (reason) {
        if (active) {
          setPerformanceError(reason instanceof Error ? reason.message : 'Unable to load account performance.');
        }
      } finally {
        inFlight = false;
        if (active) setPerformanceBusy(false);
      }
    };
    setPerformance(null);
    setPerformanceError('');
    void fetchPerformance();
    const timer = window.setInterval(() => void fetchPerformance(), botOnly ? 10_000 : 30_000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [accountId, accountType, activeContractId, botOnly, load, view]);

  const closes = candles.map((candle) => Number(candle.close));
  const fastEma = ema(closes, 9);
  const slowEma = ema(closes, 21);
  const lastFast = fastEma[fastEma.length - 1];
  const lastSlow = slowEma[slowEma.length - 1];
  const previousFast = fastEma[fastEma.length - 2];
  const previousSlow = slowEma[slowEma.length - 2];
  const trend = closes.length < 21
    ? 'Insufficient history'
    : lastFast > lastSlow
      ? previousFast <= previousSlow ? 'Bullish crossover' : 'Bullish'
      : previousFast >= previousSlow ? 'Bearish crossover' : 'Bearish';

  const low = candles.length
    ? Math.min(...candles.map((candle) => Number(candle.low)))
    : 0;
  const high = candles.length
    ? Math.max(...candles.map((candle) => Number(candle.high)))
    : 1;
  const y = (price: number) => 220 - (price - low) / (high - low || 1) * 190;
  const x = (index: number) => 15 + index * 700 / Math.max(1, candles.length - 1);
  const fastPath = fastEma.map((price, index) => `${index ? 'L' : 'M'}${x(index)},${y(price)}`).join(' ');
  const slowPath = slowEma.map((price, index) => `${index ? 'L' : 'M'}${x(index)},${y(price)}`).join(' ');
  const selectedTick = selectedMarket ? ticks[selectedMarket.symbol] : undefined;
  const digits = selectedMarket ? decimalPlaces(selectedMarket.pip_size) : 5;
  const recentActivities: AccountActivity[] = performance ? [
    ...performance.open_positions.map((position) => ({
      id: `open-${position.contract_id}`,
      contractId: position.contract_id,
      symbol: position.symbol,
      contract_type: position.contract_type,
      label: 'Open · current P&L' as const,
      time: position.purchase_time ?? 'Unavailable',
      profit: position.profit,
    })),
    ...performance.recent_closed.map((position, index) => ({
      id: `closed-${position.contract_id}-${position.sell_time}-${index}`,
      contractId: position.contract_id,
      symbol: position.symbol,
      contract_type: position.contract_type,
      label: 'Closed · realized P&L' as const,
      time: position.sell_time ?? 'Unavailable',
      profit: position.profit,
    })),
  ].sort((a, b) => timestamp(b.time) - timestamp(a.time)) : [];

  const botIds = new Set(performance?.bot_contract_ids ?? []);
  const botOpen = performance?.open_positions.filter((position) => botIds.has(position.contract_id)) ?? [];
  const botClosed = performance?.recent_closed.filter((position) => botIds.has(position.contract_id)) ?? [];
  const botProfit = botClosed.reduce((total, position) => total + Number(position.profit), 0);
  const botWins = botClosed.filter((position) => Number(position.profit) > 0).length;
  const incomplete = !!performance?.bot_tracking_unavailable || !!performance?.unresolved_bot_contract_ids?.length;

  if (botOnly) {
    const currency = performance?.currency ?? 'USD';
    return (
      <section className="accountPerformance" aria-labelledby="bot-results-heading">
        <h2 id="bot-results-heading">Demo bot results</h2>
        {performanceError && <p className="realError" role="alert">{performanceError}</p>}
        {incomplete && <p role="status">Some bot results are awaiting confirmation from Deriv.</p>}
        <div className="accountPnlCards">
          <article><span>Realized P&amp;L</span><strong>{botClosed.length ? amount(String(botProfit), currency, true) : '—'}</strong><small>{botClosed.length} confirmed settlements</small></article>
          <article><span>Win rate</span><strong>{botClosed.length ? `${(100 * botWins / botClosed.length).toFixed(1)}%` : '—'}</strong><small>{botWins} wins</small></article>
          <article><span>Open P&amp;L</span><strong>{botOpen.length ? amount(String(botOpen.reduce((sum, position) => sum + Number(position.profit), 0)), currency, true) : '—'}</strong><small>{botOpen.length} open contracts</small></article>
          <article><span>Deriv demo balance</span><strong>{amount(accountBalance, currency)}</strong></article>
        </div>
        <div className="accountMarketTableWrap accountRecentActivities">
          <table className="accountMarketTable">
            <thead><tr><th>Contract ID</th><th>Market</th><th>Activity</th><th>Time</th><th>P&amp;L</th></tr></thead>
            <tbody>
              {recentActivities.filter((activity) => botIds.has(activity.contractId)).map((activity) => (
                <tr key={activity.id}>
                  <td>{activity.contractId}</td><td>{activity.symbol}</td><td>{activity.label}</td>
                  <td>{formatTime(activity.time)}</td><td>{amount(activity.profit, currency, true)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    );
  }

  function exportPerformance() {
    if (!performance) return;
    const rows = [
      ['Account', 'Currency', 'Market', 'Contract type', 'Activity', 'Timestamp (UTC)', 'Profit / loss'],
      ...recentActivities.map((activity) => [
        performance.account_id, performance.currency, activity.symbol, activity.contract_type,
        activity.label, timestamp(activity.time) ? new Date(timestamp(activity.time)).toISOString() : '',
        activity.profit,
      ]),
    ];
    const csv = rows.map((row) => row.map((field) => `"${field.replace(/"/g, '""')}"`).join(',')).join('\r\n');
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = `playgo-pnl-${performance.account_id}.csv`;
    link.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  return (
    <>
      {view === 'markets' && (
      <section id="forex-markets" className="accountMarkets" aria-labelledby="account-markets-heading">
        <div className="accountMarketsHeading">
          <div>
            <h2 id="account-markets-heading">Forex markets</h2>
            <p>Deriv active Forex symbols · live prices · read-only for demo and real accounts</p>
            <small className="accountFeedState" role="status">{feedState}</small>
          </div>
          <div className="accountMarketControls">
            <label>
              Market
              <select value={pair} onChange={(event) => setPair(event.target.value)} disabled={!markets.length}>
                {markets.map((market) => (
                  <option key={market.symbol} value={market.pair}>{market.display_name}</option>
                ))}
              </select>
            </label>
            <label>
              Interval
              <select value={interval} onChange={(event) => setInterval(event.target.value)}>
                {INTERVALS.map((item) => (
                  <option key={item.seconds} value={item.seconds}>{item.label}</option>
                ))}
              </select>
            </label>
          </div>
        </div>

        {catalogError ? (
          <p className="realError" role="alert">{catalogError}</p>
        ) : selectedMarket ? (
          <div className="accountMarketSummary">
            <strong>{selectedMarket.display_name}</strong>
            <span>Last {selectedTick ? selectedTick.quote.toFixed(digits) : '—'}</span>
            <span>EMA 9/21: {trend}</span>
            <span>{marketStatus(selectedMarket)}</span>
          </div>
        ) : (
          <p className="accountMarketMessage">Loading active Forex markets...</p>
        )}

        {chartBusy ? (
          <p className="accountMarketMessage" role="status">Loading market history...</p>
        ) : chartError ? (
          <p className="realError" role="alert">{chartError}</p>
        ) : candles.length ? (
          <>
            <svg
              viewBox="0 0 800 260"
              role="img"
              aria-label={`${selectedMarket?.display_name ?? pair} historical candles with EMA 9 and EMA 21`}
            >
              <title>{selectedMarket?.display_name ?? pair} Deriv historical prices and EMA trend</title>
              {[0, 1, 2, 3, 4].map((step) => (
                <g key={step}>
                  <line x1="10" x2="720" y1={30 + step * 47.5} y2={30 + step * 47.5} stroke="#26374a" />
                  <text x="728" y={34 + step * 47.5} fill="#93a5bc" fontSize="10">
                    {(high - (high - low) * step / 4).toFixed(digits)}
                  </text>
                </g>
              ))}
              {candles.map((candle, index) => {
                const open = y(Number(candle.open));
                const close = y(Number(candle.close));
                const color = Number(candle.close) >= Number(candle.open) ? '#72e6ae' : '#ff8994';
                return (
                  <g key={candle.epoch}>
                    <title>
                      {new Date(candle.epoch * 1000).toLocaleString()}
                      {' | O '}{candle.open}{' H '}{candle.high}{' L '}{candle.low}{' C '}{candle.close}
                    </title>
                    <line x1={x(index)} x2={x(index)} y1={y(Number(candle.high))} y2={y(Number(candle.low))} stroke={color} />
                    <rect
                      x={x(index) - 2}
                      width="4"
                      y={Math.min(open, close)}
                      height={Math.max(1, Math.abs(open - close))}
                      fill={color}
                    />
                  </g>
                );
              })}
              {fastPath && <path d={fastPath} fill="none" stroke="#f3c969" strokeWidth="1.5" />}
              {slowPath && <path d={slowPath} fill="none" stroke="#83a9ff" strokeWidth="1.5" />}
            </svg>
            <div className="accountMarketLegend"><span>EMA 9</span><span>EMA 21</span></div>
            <div className="accountMarketDates">
              <span>{new Date(candles[0].epoch * 1000).toLocaleString()}</span>
              <span>{new Date(candles[candles.length - 1].epoch * 1000).toLocaleString()}</span>
            </div>
          </>
        ) : (
          <p className="accountMarketMessage">No candle history available.</p>
        )}

        <div className="accountMarketDirectory">
          <div className="accountMarketDirectoryHeading">
            <h3>Forex markets ({visibleMarkets.length})</h3>
            <label>
              Market status
              <select value={status} onChange={(event) => setStatus(event.target.value)}>
                <option value="All">All statuses</option>
                <option>Open</option>
                <option>Closed</option>
                <option>Suspended</option>
              </select>
            </label>
            <label>
              Find a pair
              <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search pair" />
            </label>
          </div>
          <div className="accountMarketTableWrap">
            <table className="accountMarketTable">
              <thead><tr><th>Market</th><th>Status</th><th>Bid</th><th>Ask</th><th>Last</th></tr></thead>
              <tbody>
                {!visibleMarkets.length && <tr><td colSpan={5}>No markets match the current filters.</td></tr>}
                {visibleMarkets.map((market) => {
                  const tick = ticks[market.symbol];
                  const places = decimalPlaces(market.pip_size);
                  return (
                    <tr key={market.symbol} className={pair === market.pair ? 'selectedMarketRow' : ''}>
                      <td><button type="button" onClick={() => setPair(market.pair)}>{market.display_name}</button></td>
                      <td>{marketStatus(market)}</td>
                      <td>{tick?.bid?.toFixed(places) ?? '—'}</td>
                      <td>{tick?.ask?.toFixed(places) ?? '—'}</td>
                      <td>{tick?.quote.toFixed(places) ?? '—'}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
        <p className="accountMarketNote">
          EMA 9/21 is an indicator, not a prediction. Quotes stream from Deriv; candle history refreshes every minute. No orders are placed here.
        </p>
      </section>
      )}

      {view === 'performance' && accountId && (
      <section id="profit-loss-exposure" className="accountPerformance" aria-labelledby="account-performance-heading">
        <div className="accountPerformanceHeading">
          <div>
            <h2 id="account-performance-heading">Profit, loss &amp; hedge exposure</h2>
            <p>{accountType === 'real' ? 'Real account' : 'Demo account'} · {performance?.currency ?? ''} · read-only</p>
          </div>
          <small role="status">
            {performanceBusy && !performance ? 'Loading account data...' : performance?.observed_at
              ? `Updated ${new Date(performance.observed_at).toLocaleTimeString()}`
              : 'Refreshes every 30 seconds'}
          </small>
        </div>
        {performanceError && <p className="realError" role="alert">{performanceError}</p>}
        {incomplete && <p role="status">Some bot results are awaiting confirmation from Deriv. Totals reflect confirmed data.</p>}
        {!performance && !performanceError && <p className="accountMarketMessage" role="status">Loading open positions and closed results...</p>}
        {performance && (
          <>
            <div className="accountPnlCards">
              <article><span>Deriv balance</span><strong>{amount(accountBalance, performance.currency)}</strong><small>{performance.account_id}</small></article>
              <article><span>Unrealized P&amp;L</span><strong>{amount(performance.unrealized_pnl, performance.currency, true)}</strong><small>Current open positions</small></article>
              <article><span>Realized P&amp;L</span><strong>{incomplete && !performance.realized_transaction_count ? '—' : amount(performance.realized_pnl, performance.currency, true)}</strong><small>{performance.realized_transaction_count} closed contracts · {performance.realized_window}</small></article>
            </div>
            {performance.realized_may_be_truncated && (
              <p className="accountMarketNote">The realized total may cover only the most recent transactions returned by Deriv.</p>
            )}

            <div className="accountPerformanceSection">
              <h3>Open positions ({performance.open_positions.length})</h3>
              {performance.open_positions.length ? (
                <div className="accountMarketTableWrap">
                  <table className="accountMarketTable">
                    <thead><tr><th>Market</th><th>Contract</th><th>Direction</th><th>Stake</th><th>Open P&amp;L</th></tr></thead>
                    <tbody>{performance.open_positions.map((position) => (
                      <tr key={position.contract_id}>
                        <td>{position.symbol}</td><td>{position.contract_type}</td><td>{position.direction.toUpperCase()}</td>
                        <td>{amount(position.buy_price, performance.currency)}</td>
                        <td>{amount(position.profit, performance.currency, true)}</td>
                      </tr>
                    ))}</tbody>
                  </table>
                </div>
              ) : <p className="accountMarketMessage">No open positions in this account.</p>}
            </div>

            <div className="accountPerformanceSection">
              <h3>Opposing positions by market</h3>
              {performance.opposing_exposure.length ? (
                <div className="accountMarketTableWrap">
                  <table className="accountMarketTable">
                    <thead><tr><th>Market</th><th>Up stake</th><th>Down stake</th><th>Other</th><th>Opposing amount</th></tr></thead>
                    <tbody>{performance.opposing_exposure.map((exposure) => (
                      <tr key={exposure.symbol}>
                        <td>{exposure.symbol}</td>
                        <td>{amount(exposure.up_stake, performance.currency)} ({exposure.up_count})</td>
                        <td>{amount(exposure.down_stake, performance.currency)} ({exposure.down_count})</td>
                        <td>{amount(exposure.other_stake, performance.currency)} ({exposure.other_count})</td>
                        <td>{amount(exposure.opposing_stake, performance.currency)}</td>
                      </tr>
                    ))}</tbody>
                  </table>
                </div>
              ) : <p className="accountMarketMessage">No open positions to compare.</p>}
              <p className="accountMarketNote">{performance.exposure_note}</p>
            </div>

            <div className="accountPerformanceSection">
              <h3>Recent activities ({recentActivities.length})</h3>
              <div><button type="button" className="exportCsvBtn" onClick={exportPerformance} disabled={!recentActivities.length}>Export Deriv P&amp;L CSV</button></div>
              {recentActivities.length ? (
                <div className="accountMarketTableWrap accountRecentActivities">
                  <table className="accountMarketTable">
                    <thead><tr><th>Market</th><th>Contract</th><th>Activity</th><th>Time</th><th>Profit / loss</th></tr></thead>
                    <tbody>{recentActivities.map((activity) => (
                      <tr key={activity.id}>
                        <td>{activity.symbol}</td><td>{activity.contract_type}</td>
                        <td>{activity.label}</td><td>{formatTime(activity.time)}</td>
                        <td>{amount(activity.profit, performance.currency, true)}</td>
                      </tr>
                    ))}</tbody>
                  </table>
                </div>
              ) : <p className="accountMarketMessage">No open or closed contract activity in this account.</p>}
              <p className="accountMarketNote">
                Open P&amp;L is the latest Deriv snapshot. Closed P&amp;L is realized and comes from the latest {performance.realized_window.toLowerCase()}.
                {performance.realized_may_be_truncated ? ' Older activity may be available in Deriv account history.' : ''}
              </p>
            </div>
          </>
        )}
        <p className="accountMarketNote">
          Account figures are from Deriv and refresh every 30 seconds. Exposure is a directional comparison, not a hedge or a guarantee against loss. Real-account trading remains disabled.
        </p>
      </section>
      )}
      {view === 'performance' && !accountId && (
        <section id="profit-loss-exposure" className="accountPerformance accountPerformanceLocked">
          <h2>Account P&amp;L and hedge exposure</h2>
          <p>Sign in with Deriv and select an account to view its open positions, profit and loss, and opposing exposure.</p>
        </section>
      )}
    </>
  );
}
