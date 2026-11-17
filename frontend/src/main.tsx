import React, {useCallback,useEffect,useRef,useState} from 'react';
import {createRoot} from 'react-dom/client';
import {Activity, ArrowUpRight, ArrowRight, ShieldCheck, Wallet, LogOut, RefreshCw, LockKeyhole, Eye, EyeOff, SlidersHorizontal} from 'lucide-react';
import './style.css';
import AccountWorkspace from './AccountWorkspace';
import TradingTerminal from './TradingTerminal';

const API=(import.meta.env.VITE_API_URL||'').trim().replace(/\/$/,'') ||
  (['localhost','127.0.0.1'].includes(location.hostname)?'http://127.0.0.1:8001':'');
const KEY='playgo_owner_session';
const TRADE_AMOUNT_KEY='playgo_paper_trade_amount_usd';
type Quote={bid:number;ask:number;pip:number;spread:number};
type Position={id:string;pair:string;side:"BUY"|"SELL";units:number;entry_price:string;stop_loss:string;opened_at:string;status:string;exit_price?:string;pnl?:string;closed_at?:string};
type Reconciliation={consistent:boolean;balances_cents:Record<string,number>;issues:string[]};
type PaperState={revision:number;balance:number;starting_balance:number;paused:boolean;feed_type:string;ticks:number;last_cycle_at:string|null;quotes:Record<string,Quote>;positions:Position[];trades:Position[];logs:{id:string;time:string;agent:string;message:string}[];risk_lock_reason:string|null;loss_streak:number};
type Order={client_order_id:string;status:string;request:{pair:string;side:string;units:number;bid:string;ask:string;slippage_pips:string};fill:Record<string,unknown>|null;created_at:string;updated_at:string};
type OrderPage={mode:string;total:number;limit:number;offset:number;orders:Order[]};
type Analytics={mode:string;feed_type:string;paper:{balance:number;starting_balance:number;revision:number;observations:number;paused:boolean;risk_lock_reason:string|null;open_positions:number;closed_trade_records:number};demo_orders:{total:number;by_status:Record<string,number>;by_pair:Record<string,number>};performance:{realized_pnl:null;unrealized_pnl:null;win_rate:null;max_drawdown:null;equity_curve:null;availability:string};disclaimer:string};
type ResearchTrade={side:string;entry_epoch:number;exit_epoch:number;entry_price:string;exit_price:string;units:number;estimated_costs:string;net_pnl:string;exit_reason:string};
type ResearchResult={mode:string;execution:string;pair:string;candles:number;data_source:string;granularity_seconds:number;cost_filter:{eligible:boolean;status:string;message:string};metrics:{starting_balance:string;ending_balance:string;net_pnl:string;gross_pnl:string;estimated_costs:string;return_percent:string;trade_count:number;win_rate_percent:string|null;max_closed_trade_drawdown:string;max_closed_trade_drawdown_percent:string};trades:ResearchTrade[];caveats:string[]};
type DailyLossBudget={limit_usd:string;realized_losses_usd:string;open_risk_usd:string;used_usd:string;remaining_usd:string;session_date_utc:string};
const showDate=(value:string)=>{const date=new Date(value);return Number.isNaN(date.getTime())?value:date.toLocaleString()};
async function request(path:string,token='',method='GET',body?:unknown){
 const r=await fetch(API+path,{method,cache:'no-store',headers:{...(token?{Authorization:'Bearer '+token}:{}),...(body!==undefined?{'Content-Type':'application/json'}:{})},body:body===undefined?undefined:JSON.stringify(body)});
 const data=await r.json().catch(()=>({}));
 if(!r.ok)throw new Error(r.status===401?'SESSION_EXPIRED':typeof data.detail==='string'?data.detail:'HTTP '+r.status);
 return data;
}
function ResearchPanel({token,onSessionExpired}:{token:string;onSessionExpired:()=>void}){
 const [pair,setPair]=useState('EURUSD'),[granularity,setGranularity]=useState('300'),[count,setCount]=useState(500),[lookback,setLookback]=useState(20);
 const [riskPercent,setRiskPercent]=useState('0.5'),[stopAtr,setStopAtr]=useState('1.5'),[rewardRisk,setRewardRisk]=useState('2');
 const [estimatedSpread,setEstimatedSpread]=useState('0.5'),[maxSpread,setMaxSpread]=useState('1.5'),[slippage,setSlippage]=useState('0.1');
 const [result,setResult]=useState<ResearchResult|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const money=(value:string)=>'$'+Number(value).toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2});
 async function run(e:React.FormEvent){
  e.preventDefault();setBusy(true);setError('');
  const params=new URLSearchParams({pair,granularity,count:String(count),lookback:String(lookback),risk_percent:riskPercent,stop_atr_multiple:stopAtr,reward_risk:rewardRisk,estimated_spread_pips:estimatedSpread,max_spread_pips:maxSpread,slippage_pips:slippage});
  try{setResult(await request('/api/research/breakout?'+params.toString(),token))}
  catch(e){if((e as Error).message==='SESSION_EXPIRED')onSessionExpired();else setError((e as Error).message)}
  finally{setBusy(false)}
 }
 return <div className="viewContent"><div className="viewHeading"><div><h2>Paper research lab</h2><p>Read-only Deriv candle history · no order placement</p></div><span className="pill">RESEARCH ONLY</span></div>
 <section className="panel"><div className="panelTitle"><h3>Breakout backtest</h3><span>EURUSD / GBPUSD</span></div>
 <p>Tests a close-confirmed range breakout using the next candle open, ATR-based stop and a fixed reward/risk target. Parameters are research controls, not recommendations.</p>
 <div className="researchNotice"><b>Data limitation</b><span>Deriv candle history has no order-book depth or bid/ask spread. The spread gate below uses your estimate only; it is not a live liquidity check. No market-order commands are sent and account state is unchanged.</span></div>
 <form className="modalFields researchForm" onSubmit={run}>
 <label>Pair<select value={pair} onChange={e=>setPair(e.target.value)}><option>EURUSD</option><option>GBPUSD</option></select></label>
 <label>Candle interval<select value={granularity} onChange={e=>setGranularity(e.target.value)}><option value="60">1 minute</option><option value="300">5 minutes</option><option value="900">15 minutes</option><option value="3600">1 hour</option></select></label>
 <label>History candles<input type="number" min="50" max="1000" required value={count} onChange={e=>setCount(Number(e.target.value))}/></label>
 <label>Breakout lookback<input type="number" min="5" max="100" required value={lookback} onChange={e=>setLookback(Number(e.target.value))}/></label>
 <label>Risk budget (% of test balance)<input type="number" min="0.1" max="1" step="0.1" required value={riskPercent} onChange={e=>setRiskPercent(e.target.value)}/></label>
 <label>Stop distance (ATR multiple)<input type="number" min="0.5" max="5" step="0.1" required value={stopAtr} onChange={e=>setStopAtr(e.target.value)}/></label>
 <label>Reward / risk target<input type="number" min="0.5" max="4" step="0.1" required value={rewardRisk} onChange={e=>setRewardRisk(e.target.value)}/></label>
 <label>Estimated spread (pips)<input type="number" min="0" max="10" step="0.1" required value={estimatedSpread} onChange={e=>setEstimatedSpread(e.target.value)}/></label>
 <label>Maximum assumed spread (pips)<input type="number" min="0" max="10" step="0.1" required value={maxSpread} onChange={e=>setMaxSpread(e.target.value)}/></label>
 <label>Slippage estimate (pips per side)<input type="number" min="0" max="5" step="0.1" required value={slippage} onChange={e=>setSlippage(e.target.value)}/></label>
 <button className="primary" disabled={busy||count<50||count>1000||lookback<5||lookback>100}>{busy?'Fetching public history…':'Run offline backtest'}</button>
 </form>{error&&<div className="error" role="alert">{error}</div>}
 </section>
 {result&&<><div className="simpleStats"><article><small>Net P&amp;L</small><strong>{money(result.metrics.net_pnl)}</strong></article><article><small>Closed trades</small><strong>{result.metrics.trade_count}</strong></article><article><small>Win rate</small><strong>{result.metrics.win_rate_percent===null?'N/A':result.metrics.win_rate_percent+'%'}</strong></article><article><small>Closed-trade max drawdown</small><strong>{money(result.metrics.max_closed_trade_drawdown)} · {result.metrics.max_closed_trade_drawdown_percent}%</strong></article></div>
 <section className="panel"><div className="panelTitle"><h3>Results · {result.pair}</h3><span>{result.candles} candles · {result.granularity_seconds}s</span></div>
 <div className="analyticsColumns"><div className="simpleItem"><b>Ending test balance</b><span>{money(result.metrics.ending_balance)}</span></div><div className="simpleItem"><b>Return</b><span>{result.metrics.return_percent}%</span></div><div className="simpleItem"><b>Gross P&amp;L</b><span>{money(result.metrics.gross_pnl)}</span></div><div className="simpleItem"><b>Estimated costs</b><span>{money(result.metrics.estimated_costs)}</span></div></div>
 <div className="researchNotice"><b>Cost filter: {result.cost_filter.eligible?'PASS — assumption only':'BLOCKED — assumption exceeds limit'}</b><span>{result.cost_filter.message}</span></div>
 {result.trades.length===0?<p className="empty">No trades passed the selected rules in this sample.</p>:<div className="researchTable"><div className="researchTableHead"><span>Side</span><span>Entry</span><span>Exit</span><span>Units</span><span>Net P&amp;L</span><span>Reason</span></div>{result.trades.slice(-10).reverse().map((trade,index)=><div className="researchTableRow" key={trade.entry_epoch+'-'+index}><b>{trade.side}</b><span>{showDate(new Date(trade.entry_epoch*1000).toISOString())}</span><span>{showDate(new Date(trade.exit_epoch*1000).toISOString())}</span><span>{trade.units}</span><span>{money(trade.net_pnl)}</span><span>{trade.exit_reason}</span></div>)}</div>}
 <ul className="researchCaveats">{result.caveats.map(note=><li key={note}>{note}</li>)}</ul>
 </section></>}
 </div>
}
function LegacyApp(){
 const [token,setToken]=useState(()=>sessionStorage.getItem(KEY)||'');
 const [username,setUsername]=useState('playgo_admin'),[password,setPassword]=useState('');
 const [state,setState]=useState<PaperState|null>(null),[account,setAccount]=useState<{role:string;mode:string}|null>(null);
 const [orders,setOrders]=useState<Order[]>([]),[pair,setPair]=useState('EURUSD'),[side,setSide]=useState('BUY'),[units,setUnits]=useState(1000);
 const [busy,setBusy]=useState(false),[error,setError]=useState(''),[message,setMessage]=useState('');
 const [tab,setTab]=useState<'dashboard'|'positions'|'history'|'analytics'|'research'>('dashboard');
 const [history,setHistory]=useState<OrderPage|null>(null),[historyBusy,setHistoryBusy]=useState(false),[historyError,setHistoryError]=useState('');
 const [historyPage,setHistoryPage]=useState(0),[historyPair,setHistoryPair]=useState(''),[historySide,setHistorySide]=useState(''),[historyStatus,setHistoryStatus]=useState(''),[dateFrom,setDateFrom]=useState(''),[dateTo,setDateTo]=useState('');
 const [selectedOrder,setSelectedOrder]=useState<Order|null>(null);
 const [analytics,setAnalytics]=useState<Analytics|null>(null),[analyticsBusy,setAnalyticsBusy]=useState(false),[analyticsError,setAnalyticsError]=useState('');
 const [reconciliation,setReconciliation]=useState<Reconciliation|null>(null),[reconciliationBusy,setReconciliationBusy]=useState(false),[reconciliationError,setReconciliationError]=useState("");
 const [positionPair,setPositionPair]=useState("EURUSD"),[positionSide,setPositionSide]=useState<"BUY"|"SELL">("BUY"),[positionUnits,setPositionUnits]=useState(1000),[stopLoss,setStopLoss]=useState("");
 const [positionError,setPositionError]=useState(""),[positionMessage,setPositionMessage]=useState("");
 const pageSize=20;
 const logoutLocal=useCallback(()=>{sessionStorage.removeItem(KEY);setToken('');setState(null);setAccount(null);setOrders([]);setHistory(null);setSelectedOrder(null);setAnalytics(null);setReconciliation(null);setReconciliationError('');setPassword('')},[]);
 const refresh=useCallback(async(t=token)=>{
  if(!t||!API)return;
  try{
   const [a,s]=await Promise.all([request('/api/identity/me/paper-account',t),request('/api/state',t)]);
   setAccount(a);setState(s.state);setError('');
  }catch(e){if((e as Error).message==='SESSION_EXPIRED')logoutLocal();else setError((e as Error).message)}
 },[token,logoutLocal]);
 useEffect(()=>{if(!token)return;void refresh();const timer=setInterval(()=>void refresh(),15000);return()=>clearInterval(timer)},[token,refresh]);
 const loadReconciliation=useCallback(async()=>{if(!token)return;setReconciliationBusy(true);setReconciliationError('');try{setReconciliation(await request('/api/accounting/reconciliation',token))}catch(e){setReconciliation(null);setReconciliationError((e as Error).message)}finally{setReconciliationBusy(false)}},[token]);
 useEffect(()=>{if(tab==='positions'&&token)void loadReconciliation()},[tab,token,loadReconciliation]);
 async function openPosition(e:React.FormEvent){e.preventDefault();if(!state)return;setBusy(true);setPositionError('');setPositionMessage('');try{
  const result=await request('/api/paper/positions',token,'POST',{position_id:'paper-'+crypto.randomUUID(),expected_revision:state.revision,pair:positionPair,side:positionSide,units:positionUnits,stop_loss:stopLoss});
  setPositionMessage('PAPER position '+result.position.id+' opened');await refresh();await loadReconciliation();
 }catch(e){setPositionError((e as Error).message);await refresh()}finally{setBusy(false)}}
 async function closePosition(id:string){if(!state||!window.confirm('Close PAPER position '+id+' at the latest synthetic bid/ask?'))return;setBusy(true);setPositionError('');setPositionMessage('');try{
  const result=await request('/api/paper/positions/'+encodeURIComponent(id)+'/close',token,'POST',{expected_revision:state.revision});
  setPositionMessage('PAPER position closed; realized P&L $'+result.position.pnl);await refresh();await loadReconciliation();
 }catch(e){setPositionError((e as Error).message);await refresh()}finally{setBusy(false)}}
 const paperPnl=(p:Position)=>{const q=state?.quotes[p.pair];if(!q)return null;const exit=p.side==='BUY'?q.bid:q.ask;return Math.round((exit-Number(p.entry_price))*p.units*(p.side==='BUY'?1:-1)*100)/100};
 const accountingAligned=!!(state&&reconciliation?.consistent&&Math.round(state.balance*100)===reconciliation.balances_cents.CASH);
 const loadHistory=useCallback(async()=>{
  if(!token||!API)return;
  setHistoryBusy(true);setHistoryError('');
  try{
   const params=new URLSearchParams({limit:String(pageSize),offset:String(historyPage*pageSize)});
   if(historyPair)params.set('pair',historyPair);
   if(historySide)params.set('side',historySide);
   if(historyStatus)params.set('status',historyStatus);
   if(dateFrom)params.set('date_from',dateFrom);
   if(dateTo)params.set('date_to',dateTo);
   const data=await request('/api/demo/orders?'+params.toString(),token);
   setHistory(data);
  }catch(e){if((e as Error).message==='SESSION_EXPIRED')logoutLocal();else setHistoryError((e as Error).message)}
  finally{setHistoryBusy(false)}
 },[token,historyPage,historyPair,historySide,historyStatus,dateFrom,dateTo,logoutLocal]);
 useEffect(()=>{if(tab==='history')void loadHistory()},[tab,loadHistory]);
 const loadAnalytics=useCallback(async()=>{
  if(!token)return;
  setAnalyticsBusy(true);setAnalyticsError('');
  try{setAnalytics(await request('/api/analytics/overview',token))}
  catch(e){if((e as Error).message==='SESSION_EXPIRED')logoutLocal();else setAnalyticsError((e as Error).message)}
  finally{setAnalyticsBusy(false)}
 },[token,logoutLocal]);
 useEffect(()=>{if(tab==='analytics')void loadAnalytics()},[tab,loadAnalytics]);
 async function openOrder(id:string){setHistoryError('');try{setSelectedOrder(await request('/api/demo/orders/'+encodeURIComponent(id),token))}catch(e){if((e as Error).message==='SESSION_EXPIRED')logoutLocal();else setHistoryError((e as Error).message)}}
 async function login(e:React.FormEvent){e.preventDefault();setBusy(true);setError('');
  try{const d=await request('/api/identity/login','','POST',{username,password});if(typeof d.access_token!=='string')throw Error('Missing session token');sessionStorage.setItem(KEY,d.access_token);setToken(d.access_token);setPassword('')}
  catch(e){setError((e as Error).message)}finally{setBusy(false)}
 }
 async function logout(){setBusy(true);try{await request('/api/identity/logout',token,'POST')}catch(e){setError('Server logout not confirmed: '+(e as Error).message)}finally{logoutLocal();setBusy(false)}}
 async function changeState(paused:boolean){if(!state)return;setBusy(true);setError('');try{const d=await request('/api/state/control',token,'POST',{expected_revision:state.revision,paused});setState(d.state);setMessage('Paper engine '+(paused?'paused':'enabled'))}catch(e){setError((e as Error).message);await refresh()}finally{setBusy(false)}}
 async function cycle(){if(!state)return;setBusy(true);setError('');try{const d=await request('/api/auto-cycle',token,'POST',{expected_revision:state.revision});setState(d.state);setMessage('Synthetic observation completed — no order executed')}catch(e){setError((e as Error).message);await refresh()}finally{setBusy(false)}}
 async function order(e:React.FormEvent){e.preventDefault();if(!state)return;const q=state.quotes[pair];if(!q){setError('Quote unavailable');return}
  setBusy(true);setError('');try{const id='web-'+crypto.randomUUID();const d=await request('/api/demo/orders',token,'POST',{client_order_id:id,pair,side,units,bid:String(q.bid),ask:String(q.ask),slippage_pips:'0.2'});setOrders(v=>[d,...v]);setHistory(null);setMessage('DEMO order '+d.status+' — not a live broker trade')}catch(e){setError((e as Error).message)}finally{setBusy(false)}
 }
 const money=(v:number)=>'$'+v.toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2});
 if(!API)return <main className="simpleApp"><section className="panel"><h2>Backend URL not configured</h2><p>Set VITE_API_URL to the PostgreSQL FastAPI origin.</p></section></main>;
 if(!token)return <main className="simpleApp"><header className="simpleHeader"><div className="brand"><div className="logo">P</div><h1>PlayGo AI Trading</h1></div><span className="pill">PAPER ONLY</span></header><section className="panel" style={{maxWidth:460,margin:'70px auto',padding:28}}><h2>Owner sign in</h2><p>Supabase PostgreSQL · Private owner access</p><form onSubmit={login} style={{display:'grid',gap:16,marginTop:20}}><label>Username<input required autoComplete="username" value={username} onChange={e=>setUsername(e.target.value)}/></label><label>Password<input required type="password" autoComplete="current-password" value={password} onChange={e=>setPassword(e.target.value)}/></label><button className="primary" disabled={busy}>{busy?'Signing in…':'Sign in'}</button></form>{error&&<p className="error" role="alert">{error}</p>}<small>No public registration. Demo trading only.</small></section></main>;
 return <main className="simpleApp"><header className="simpleHeader"><div className="brand"><div className="logo">P</div><div><h1>PlayGo AI Trading</h1><small>POSTGRESQL PAPER ACCOUNT</small></div></div><div className="headerRight"><span className="pill">PAPER ONLY</span><button className="secondary" disabled={busy} onClick={logout}>Sign out</button></div></header>
 <nav className="historyNav" aria-label="Dashboard sections"><button type="button" className={tab==='dashboard'?'selected':''} onClick={()=>setTab('dashboard')}>Dashboard</button><button type="button" className={tab==='positions'?'selected':''} onClick={()=>setTab('positions')}>Positions</button><button type="button" className={tab==='history'?'selected':''} onClick={()=>setTab('history')}>Order history</button><button type="button" className={tab==='analytics'?'selected':''} onClick={()=>setTab('analytics')}>Analytics</button><button type="button" className={tab==='research'?'selected':''} onClick={()=>setTab('research')}>Research</button></nav>
 {tab==='research'?<ResearchPanel token={token} onSessionExpired={logoutLocal}/>:tab==='positions'?<div className="viewContent"><div className="viewHeading"><div><h2>PAPER positions</h2><p>Synthetic prices · No broker execution</p></div><button className="secondary" disabled={busy} onClick={()=>{void refresh();void loadReconciliation()}}>Refresh positions</button></div>
 {positionError&&<div className="error" role="alert">{positionError}</div>}{positionMessage&&<p role="status">{positionMessage}</p>}
 {!state?<section className="panel">Loading positions…</section>:<>
 <div className="simpleStats"><article><small>Open positions</small><strong>{state.positions.length}</strong></article><article><small>Closed trades</small><strong>{state.trades.length}</strong></article><article><small>Unrealized P&amp;L (indicative)</small><strong>{money(state.positions.reduce((total,p)=>total+(paperPnl(p)??0),0))}</strong></article><article><small>Paper cash</small><strong>{money(state.balance)}</strong></article></div>
 <section className="panel"><div className="panelTitle"><h3>Accounting integrity</h3><span className="pill">{accountingAligned?'ALIGNED':'NOT VERIFIED'}</span></div>
 <p>Journal consistency: {reconciliationError?'ERROR':reconciliationBusy?'Checking…':reconciliation===null?'Not loaded':reconciliation.consistent?'PASS':'FAIL'}. Cash comparison: {reconciliation===null?'Unavailable':money((reconciliation.balances_cents.CASH??0)/100)+' ledger / '+money(state.balance)+' state'}.</p>
 {reconciliationError&&<p className="error" role="alert">Reconciliation request failed: {reconciliationError}. Check the backend server and retry.</p>}
 {reconciliation&&reconciliation.issues.length>0&&<p className="error" role="alert">Ledger issues: {reconciliation.issues.join(', ')}</p>}
 {!accountingAligned&&<p className="error" role="alert">PAPER cash and ledger must agree before opening positions. A discrepancy does not justify deleting journals or silently adjusting balances. Existing positions remain visible.</p>}
 </section>
 <section className="panel"><div className="panelTitle"><h3>Open a PAPER position</h3><span className="pill">SYNTHETIC ONLY</span></div>
 <p>Opening uses the current synthetic ask for BUY or bid for SELL. The backend enforces exposure, stop-loss and drawdown limits.</p>
 <form className="modalFields" onSubmit={openPosition}><label>Pair<select value={positionPair} onChange={e=>{setPositionPair(e.target.value);setStopLoss('')}}><option>EURUSD</option><option>GBPUSD</option></select></label>
 <label>Direction<select value={positionSide} onChange={e=>{setPositionSide(e.target.value as "BUY"|"SELL");setStopLoss('')}}><option>BUY</option><option>SELL</option></select></label>
 <label>Units<input type="number" min="1" max="100000" required value={positionUnits} onChange={e=>setPositionUnits(Number(e.target.value))}/></label>
 <label>Stop loss<input required type="number" step="0.00001" min="0.00001" placeholder="Enter losing-side stop" value={stopLoss} onChange={e=>setStopLoss(e.target.value)}/></label>
 <button className="primary" disabled={busy||!accountingAligned||state.paused||!!state.risk_lock_reason||!Number.isSafeInteger(positionUnits)||positionUnits<1||positionUnits>100000}>Open PAPER position</button></form>
 {state.paused&&<small>The PAPER engine is paused. Enable it from Dashboard after resolving accounting integrity.</small>}
 </section>
 <section className="panel"><div className="panelTitle"><h3>Active positions</h3><span>{state.positions.length} open</span></div>
 {!state.positions.length?<p className="empty">No open PAPER positions.</p>:state.positions.map(p=><div className="positionRecord" key={p.id}><div><b>{p.pair} · {p.side}</b><small>{p.units} units · Opened {showDate(p.opened_at)}</small><small>Entry {p.entry_price} · Stop {p.stop_loss}</small><small>Unrealized P&amp;L: {paperPnl(p)===null?'Quote unavailable':money(paperPnl(p)!)}</small></div><button className="secondary" disabled={busy} onClick={()=>void closePosition(p.id)}>Close PAPER</button></div>)}
 </section>
 <section className="panel"><div className="panelTitle"><h3>Closed PAPER trades</h3><span>{state.trades.length} settled records</span></div>
 {!state.trades.length?<p className="empty">No closed PAPER trades.</p>:state.trades.slice().reverse().map(p=><div className="positionRecord" key={p.id}><div><b>{p.pair} · {p.side}</b><small>{p.units} units · {showDate(p.closed_at||'')}</small><small>Entry {p.entry_price} · Exit {p.exit_price}</small></div><strong>{p.pnl===undefined?'N/A':money(Number(p.pnl))}</strong></div>)}
 </section></>}
 </div>:tab==='analytics'?<div className="viewContent"><div className="viewHeading"><div><h2>Trading analytics</h2><p>Authoritative paper account and persisted DEMO activity</p></div><button className="secondary" disabled={analyticsBusy} onClick={()=>void loadAnalytics()}>Refresh analytics</button></div>
 {analyticsError&&<div className="error" role="alert">{analyticsError}</div>}
 {analyticsBusy&&!analytics?<section className="panel"><p>Loading analytics…</p></section>:analytics&&<>
 <div className="simpleStats"><article><small>Paper balance</small><strong>{money(analytics.paper.balance)}</strong></article><article><small>Starting capital</small><strong>{money(analytics.paper.starting_balance)}</strong></article><article><small>DEMO orders</small><strong>{analytics.demo_orders.total}</strong></article><article><small>Synthetic observations</small><strong>{analytics.paper.observations}</strong></article></div>
 <section className="panel"><div className="panelTitle"><h3>Simulated order activity</h3><span className="pill">DEMO ONLY</span></div><div className="analyticsColumns"><div><h4>By status</h4>{Object.entries(analytics.demo_orders.by_status).length===0?<p>No orders yet</p>:Object.entries(analytics.demo_orders.by_status).map(([name,count])=><div className="simpleItem" key={name}><b>{name}</b><span>{count}</span></div>)}</div><div><h4>By pair</h4>{Object.entries(analytics.demo_orders.by_pair).length===0?<p>No orders yet</p>:Object.entries(analytics.demo_orders.by_pair).map(([name,count])=><div className="simpleItem" key={name}><b>{name}</b><span>{count}</span></div>)}</div></div></section>
 <section className="panel"><div className="panelTitle"><h3>Performance metrics</h3><span>Not yet available</span></div><p>Realized P&amp;L, unrealized P&amp;L, win rate, equity curve, and maximum drawdown require a verified position lifecycle and accounting settlement. They are intentionally not estimated from DEMO fills.</p><div className="analyticsUnavailable"><span>Realized P&amp;L: N/A</span><span>Unrealized P&amp;L: N/A</span><span>Win rate: N/A</span><span>Maximum drawdown: N/A</span></div><small>{analytics.disclaimer}</small></section>
 <section className="panel"><div className="panelTitle"><h3>Paper risk snapshot</h3></div><div className="analyticsColumns"><div className="simpleItem"><b>Engine</b><span>{analytics.paper.paused?'PAUSED':'ENABLED'}</span></div><div className="simpleItem"><b>Open positions</b><span>{analytics.paper.open_positions}</span></div><div className="simpleItem"><b>Closed trade records</b><span>{analytics.paper.closed_trade_records}</span></div><div className="simpleItem"><b>Risk lock</b><span>{analytics.paper.risk_lock_reason||'None'}</span></div></div></section>
 </>}</div>:tab==='history'?<div className="viewContent"><div className="viewHeading"><div><h2>DEMO order history</h2><p>Persistent PostgreSQL records · simulated execution only</p></div><button className="secondary" disabled={historyBusy} onClick={()=>void loadHistory()}>Refresh history</button></div>
 <section className="panel"><div className="panelTitle"><h3>Filters</h3><span>UTC dates</span></div><div className="historyFilters">
 <label>Pair<select value={historyPair} onChange={e=>{setHistoryPair(e.target.value);setHistoryPage(0)}}><option value="">All pairs</option><option>EURUSD</option><option>GBPUSD</option></select></label>
 <label>Direction<select value={historySide} onChange={e=>{setHistorySide(e.target.value);setHistoryPage(0)}}><option value="">All directions</option><option>BUY</option><option>SELL</option></select></label>
 <label>Status<select value={historyStatus} onChange={e=>{setHistoryStatus(e.target.value);setHistoryPage(0)}}><option value="">All statuses</option><option>PENDING</option><option>FILLED</option></select></label>
 <label>From<input type="date" value={dateFrom} onChange={e=>{setDateFrom(e.target.value);setHistoryPage(0)}}/></label>
 <label>To<input type="date" value={dateTo} onChange={e=>{setDateTo(e.target.value);setHistoryPage(0)}}/></label>
 </div></section>
 <section className="panel"><div className="panelTitle"><h3>Orders</h3><span>{history?.total??'—'} records</span></div>
 {historyError&&<div className="error" role="alert">{historyError}</div>}
 {historyBusy?<p>Loading history…</p>:!history?.orders.length?<p className="empty">No DEMO orders match these filters.</p>:<div className="historyTable"><div className="historyTableHead"><span>Placed</span><span>Pair / direction</span><span>Units</span><span>Status</span><span>Details</span></div>{history.orders.map(o=><div className="historyTableRow" key={o.client_order_id}><span>{showDate(o.created_at)}</span><b>{o.request.pair} · {o.request.side}</b><span>{o.request.units}</span><span>{o.status}</span><button type="button" className="secondary" onClick={()=>void openOrder(o.client_order_id)}>View</button></div>)}</div>}
 <div className="reportPagination"><small>Page {historyPage+1}{history?' · '+history.total+' total':''}</small><div><button className="secondary" disabled={historyBusy||historyPage===0} onClick={()=>setHistoryPage(p=>p-1)}>Previous</button><button className="secondary" disabled={historyBusy||!history||(historyPage+1)*pageSize>=history.total} onClick={()=>setHistoryPage(p=>p+1)}>Next</button></div></div>
 </section>
 {selectedOrder&&<div className="modalBackdrop" onClick={()=>setSelectedOrder(null)}><section className="actionModal" role="dialog" aria-modal="true" aria-label="DEMO order details" onClick={e=>e.stopPropagation()}><div className="panelTitle"><h3>DEMO order details</h3><button className="secondary" onClick={()=>setSelectedOrder(null)}>Close</button></div><dl className="orderDetails"><dt>Order ID</dt><dd>{selectedOrder.client_order_id}</dd><dt>Status</dt><dd>{selectedOrder.status}</dd><dt>Pair / direction</dt><dd>{selectedOrder.request.pair} · {selectedOrder.request.side}</dd><dt>Units</dt><dd>{selectedOrder.request.units}</dd><dt>Bid / Ask</dt><dd>{selectedOrder.request.bid} / {selectedOrder.request.ask}</dd><dt>Requested slippage (pips)</dt><dd>{selectedOrder.request.slippage_pips}</dd><dt>Created</dt><dd>{showDate(selectedOrder.created_at)}</dd><dt>Updated</dt><dd>{showDate(selectedOrder.updated_at)}</dd></dl><h4>Simulated execution</h4><pre className="fillDetails">{selectedOrder.fill?JSON.stringify(selectedOrder.fill,null,2):'Not filled'}</pre><small>No broker execution or realized P&amp;L.</small></section></div>}
 </div>:<div className="viewContent"><div className="viewHeading"><div><h2>Owner dashboard</h2><p>{account?.role||'OWNER'} · {account?.mode||'PAPER'} · Supabase-backed</p></div><button className="secondary" onClick={()=>void refresh()} disabled={busy}>Refresh</button></div>
 {error&&<div className="error" role="alert">{error}</div>}{message&&<p role="status">{message}</p>}
 {!state?<section className="panel"><p>Loading authoritative paper state…</p></section>:<>
 <div className="simpleStats"><article><small>Paper balance</small><strong>{money(state.balance)}</strong></article><article><small>Initial balance</small><strong>{money(state.starting_balance)}</strong></article><article><small>Revision</small><strong>{state.revision}</strong></article><article><small>Observations</small><strong>{state.ticks}</strong></article></div>
 <section className="panel"><div className="panelTitle"><h3>Paper engine</h3><span className="pill">{state.paused?'PAUSED':'ENABLED'}</span></div><p>Feed: {state.feed_type}. Enabling the engine does not place trades. Cycles observe synthetic prices only.</p>{state.risk_lock_reason&&<p className="error">Risk lock: {state.risk_lock_reason}</p>}<div className="simpleActions"><button className="primary" disabled={busy} onClick={()=>changeState(!state.paused)}>{state.paused?'Enable paper engine':'Pause paper engine'}</button><button className="secondary" disabled={busy} onClick={cycle}>Run synthetic cycle</button></div><small>Last cycle: {state.last_cycle_at||'Never'}</small></section>
 <section className="panel"><div className="panelTitle"><h3>Synthetic market quotes</h3><span>{Object.keys(state.quotes).length} pairs</span></div><div className="simpleTableHead"><span>Pair</span><span>Bid</span><span>Ask</span></div>{Object.entries(state.quotes).map(([name,q])=><div className="simpleTableRow" key={name}><b>{name}</b><span>{q.bid}</span><span>{q.ask}</span></div>)}</section>
 <section className="panel"><div className="panelTitle"><h3>Submit simulated DEMO order</h3><span className="pill">NO LIVE TRADING</span></div><p>Uses the currently displayed synthetic quote. Fills are deterministic and persisted separately from paper account positions.</p><form onSubmit={order} className="modalFields"><label>Pair<select value={pair} onChange={e=>setPair(e.target.value)}>{Object.keys(state.quotes).map(x=><option key={x}>{x}</option>)}</select></label><label>Direction<select value={side} onChange={e=>setSide(e.target.value)}><option>BUY</option><option>SELL</option></select></label><label>Units<input type="number" min="1" max="100000" required value={units} onChange={e=>setUnits(Number(e.target.value))}/></label><button className="primary" disabled={busy||!Number.isSafeInteger(units)||units<1||units>100000}>Submit DEMO order</button></form>{orders.map(o=><div className="simpleItem" key={o.client_order_id}><b>{o.request.pair} · {o.request.side} · {o.request.units} units</b><span>{o.status}</span></div>)}</section>
 <section className="panel"><div className="panelTitle"><h3>Recent state events</h3></div>{state.logs.length===0?<p className="empty">No events yet</p>:state.logs.slice(0,15).map(l=><div className="simpleItem" key={l.id}><div><b>{l.agent}</b><small>{l.message}</small></div><small>{l.time}</small></div>)}</section>
 </>}</div>}<footer>PlayGo Tanzania · Paper only · No live brokerage connection</footer></main>
}
function App(){
 const [token,setToken]=useState(()=>sessionStorage.getItem(KEY)||'');
 const [showPassword,setShowPassword]=useState(false);
 const [refreshing,setRefreshing]=useState(false),[lastUpdated,setLastUpdated]=useState<Date|null>(null);
 const [username,setUsername]=useState('playgo_admin'),[password,setPassword]=useState('');
 const [tradeAmount,setTradeAmount]=useState(()=>{
  const saved=localStorage.getItem(TRADE_AMOUNT_KEY);
  return saved&&/^\d+(?:\.\d{1,2})?$/.test(saved)&&Number(saved)>=0.01&&Number(saved)<=100000?saved:'10';
 });
 const [savedTradeAmount,setSavedTradeAmount]=useState(tradeAmount);
 const [amountApplied,setAmountApplied]=useState(false);
 const [state,setState]=useState<PaperState|null>(null),[dailyRisk,setDailyRisk]=useState<DailyLossBudget|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const logoutLocal=useCallback(()=>{sessionStorage.removeItem(KEY);setToken('');setState(null);setPassword('')},[]);
 const refresh=useCallback(async()=>{
  if(!token||!API)return;
  setRefreshing(true);
  try{
   const [data,status]=await Promise.all([request('/api/state',token),request('/api/paper/automation/operational-status',token)]);
   setState(data.state);setDailyRisk(status.daily_loss_budget);setLastUpdated(new Date());setError('');
  }catch(e){if((e as Error).message==='SESSION_EXPIRED')logoutLocal();else setError((e as Error).message)}finally{setRefreshing(false)}
 },[token,logoutLocal]);
 useEffect(()=>{if(!token)return;void refresh();const timer=setInterval(()=>void refresh(),15000);return()=>clearInterval(timer)},[token,refresh]);
 async function login(e:React.FormEvent){
  e.preventDefault();setBusy(true);setError('');
  try{const data=await request('/api/identity/login','','POST',{username,password});if(typeof data.access_token!=='string')throw Error('Missing session token');sessionStorage.setItem(KEY,data.access_token);setToken(data.access_token);setPassword('')}
  catch(e){setError((e as Error).message)}finally{setBusy(false)}
 }
 async function logout(){
  setBusy(true);
  try{await request('/api/identity/logout',token,'POST')}
  catch(e){setError('Server logout not confirmed: '+(e as Error).message)}
  finally{logoutLocal();setBusy(false)}
 }
 const loadTerminal=useCallback((path:string)=>request(path,token),[token]);
 const amountValue=Number(tradeAmount);
 const amountValid=/^\d+(?:\.\d{1,2})?$/.test(tradeAmount)&&Number.isFinite(amountValue)&&amountValue>=0.01&&amountValue<=100000;
 const amountChanged=amountValue!==Number(savedTradeAmount);
 function applyTradeAmount(e:React.FormEvent){
  e.preventDefault();
  if(!amountValid||!amountChanged)return;
  try{
   localStorage.setItem(TRADE_AMOUNT_KEY,tradeAmount);
   setSavedTradeAmount(tradeAmount);setAmountApplied(true);
  }catch{setError('Unable to save the amount. Check your browser storage settings and try again.')}
 }
 const money=(value:number)=>'$'+value.toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2});
 const paperPnl=(position:Position):number|null=>{
  const quote=state?.quotes[position.pair];
  if(!quote)return null;
  const exit=position.side==='BUY'?quote.bid:quote.ask;
  const pnl=(exit-Number(position.entry_price))*position.units*(position.side==='BUY'?1:-1);
  return Number.isFinite(pnl)?Math.round(pnl*100)/100:null;
 };
 const realizedPnl=state?.trades.reduce((total,trade)=>{
  const pnl=Number(trade.pnl);
  return Number.isFinite(pnl)?total+pnl:total;
 },0)??0;
 const openPnl=state?.positions.reduce((total,position)=>total+(paperPnl(position)??0),0)??0;
 const totalPnl=realizedPnl+openPnl;
 const dailyRiskUsed=dailyRisk?Number(dailyRisk.used_usd):0;
 const dailyRiskLimit=dailyRisk?Number(dailyRisk.limit_usd):0;
 const dailyRiskPercent=dailyRiskLimit>0?Math.min(100,Math.max(0,dailyRiskUsed/dailyRiskLimit*100)):0;
 const riskOverBudget=dailyRiskUsed>dailyRiskLimit;
 const [pnlLog,setPnlLog]=useState<{id:string;pair:string;side:string;time:string;kind:'profit'|'loss';pnl:number}[]>([]);
 const activity: {id:string;pair:string;side:string;time:string;kind:'open'|'profit'|'loss'|'flat';pnl:number|null}[]=state?[
  ...pnlLog,
  ...state.positions.map(position=>({id:'open-'+position.id,pair:position.pair,side:position.side,time:position.opened_at,kind:'open' as const,pnl:paperPnl(position)})),
  ...state.trades.map(trade=>{
   const pnl=Number(trade.pnl);
   const validPnl=Number.isFinite(pnl)?pnl:null;
   return {id:'closed-'+trade.id,pair:trade.pair,side:trade.side,time:trade.closed_at||trade.opened_at,kind:validPnl===null||validPnl===0?'flat' as const:validPnl>0?'profit' as const:'loss' as const,pnl:validPnl};
  }),
 ].sort((a,b)=>Date.parse(b.time)-Date.parse(a.time)).slice(0,8):[];
 const previousTotalPnl=useRef<number|null>(null);
 const [pnlPulse,setPnlPulse]=useState<'up'|'down'|'none'>('none');
 const [profitNotice,setProfitNotice]=useState<{id:number;gain:number}|null>(null);
 const profitNoticeTimer=useRef<number|undefined>(undefined);
 useEffect(()=>()=>window.clearTimeout(profitNoticeTimer.current),[]);
 useEffect(()=>{
  if(!state){previousTotalPnl.current=null;setProfitNotice(null);setPnlLog([]);window.clearTimeout(profitNoticeTimer.current);return;}
  const previous=previousTotalPnl.current;
  previousTotalPnl.current=totalPnl;
  if(previous===null||previous===totalPnl)return;
  const gain=Math.round((totalPnl-previous)*100)/100;
  if(gain!==0){
   const observedAt=new Date();
   setPnlLog(entries=>[{id:'pnl-'+crypto.randomUUID(),pair:'Paper P&L',side:gain>0?'Profit update':'Loss update',time:observedAt.toISOString(),kind:gain>0?'profit' as const:'loss' as const,pnl:gain},...entries].slice(0,30));
   setProfitNotice({id:observedAt.getTime(),gain});
   window.clearTimeout(profitNoticeTimer.current);
   profitNoticeTimer.current=window.setTimeout(()=>setProfitNotice(null),6000);
  }
  setPnlPulse(totalPnl>previous?'up':'down');
  const timer=window.setTimeout(()=>setPnlPulse('none'),900);
  return ()=>window.clearTimeout(timer);
 },[totalPnl,state]);
 if(!API)return <main className="simpleApp"><section className="panel"><h2>Backend URL not configured</h2><p>Set VITE_API_URL to the PostgreSQL FastAPI origin.</p></section></main>;
 if(!token)return <main className="simpleApp welcomeApp">
  <header className="simpleHeader"><div className="brand"><div className="logo"><Activity size={25}/></div><div><h1>PlayGo<span className="brandAccent">.</span></h1><small>YOUR PAPER TRADING WORKSPACE</small></div></div><span className="pill">PAPER ACCOUNT</span></header>
  <div className="loginLayout"><section className="loginIntro"><span className="eyebrow">PRACTICE WITH PERSPECTIVE</span><h2>A clearer view of<br/>your trading journey<span>.</span></h2><p>Follow your paper account, understand your risk, and keep every simulated trade in perspective.</p><div className="loginFeatures"><div><Wallet/><span><b>Your account at a glance</b><small>Balance, realized returns, and open positions.</small></span></div><div><ShieldCheck/><span><b>Risk stays in view</b><small>Track your daily paper risk budget.</small></span></div><div><Activity/><span><b>A record of every move</b><small>Recent trade activity in one workspace.</small></span></div></div><div className="loginFootnote"><ShieldCheck size={16}/> Simulated trading. No live funds.</div></section>
  <section className="panel loginCard"><div className="loginIcon"><LockKeyhole size={23}/></div><h2>Welcome back</h2><p>Sign in to your private trading workspace.</p><form onSubmit={login}><label htmlFor="username">Username<input id="username" required autoComplete="username" value={username} onChange={e=>setUsername(e.target.value)}/></label><label htmlFor="password">Password<div className="passwordField"><input id="password" required type={showPassword?'text':'password'} autoComplete="current-password" placeholder="Enter your password" value={password} onChange={e=>setPassword(e.target.value)}/><button type="button" className="passwordToggle" aria-label={showPassword?'Hide password':'Show password'} aria-pressed={showPassword} onClick={()=>setShowPassword(v=>!v)}>{showPassword?<EyeOff size={18}/>:<Eye size={18}/>}</button></div></label>{error&&<p className="error" role="alert">{error==='Failed to fetch'?'Unable to connect. Check that the server is running and try again.':error==='Authentication service unavailable'?'Sign-in is temporarily unavailable because the server could not access its authentication service. Please try signing in again.':error}</p>}<button className="primary" disabled={busy}>{busy?'Signing in...':'Sign in to workspace'}<ArrowRight size={17}/></button></form><div className="loginPrivacy"><LockKeyhole size={13}/> Private owner access / No public registration</div></section></div>
  <footer>PlayGo Trading <span>Paper trading. Real perspective.</span></footer>
 </main>;
 return <main className="simpleApp automationOnly">
  {profitNotice&&<div className={`profitToast ${profitNotice.gain<0?'lossToast':''}`} key={profitNotice.id} role="status" aria-live="polite"><div className="profitToastIcon"><ArrowUpRight size={24} style={profitNotice.gain<0?{transform:'rotate(90deg)'}:undefined}/></div><div><small>{profitNotice.gain<0?'Paper P&L decreased':'Paper P&L increased'}</small><strong>{profitNotice.gain<0?'\u2212':'+'}{money(Math.abs(profitNotice.gain))}</strong><span>Total paper P&amp;L: {money(totalPnl)}</span></div><button type="button" className="profitToastClose" aria-label="Dismiss profit notification" onClick={()=>setProfitNotice(null)}>{String.fromCharCode(215)}</button></div>}
  <header className="simpleHeader"><div className="brand"><div className="logo"><Activity size={25}/></div><div><h1>PlayGo<span className="brandAccent">.</span></h1><small>PAPER TRADING WORKSPACE</small></div></div><div className="headerRight"><span className="pill amber">PAPER / AUTOMATION OFF</span><button className="secondary" disabled={busy} onClick={logout}><LogOut size={16}/> Sign out</button></div></header>
  {error&&<div className="error" role="alert">{error}</div>}
  <section className="automationHero"><div><span className="eyebrow">YOUR WORKSPACE / OVERVIEW</span><h2>Trading overview<span className="brandAccent">.</span></h2><p>A little perspective on every paper trade.</p></div><div className="refreshGroup"><span>{lastUpdated?`Updated ${lastUpdated.toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'})}`:'Waiting for account'}</span><button className="secondary" disabled={refreshing} onClick={()=>void refresh()}><RefreshCw size={15} className={refreshing?'spin':''}/>{refreshing?'Updating...':'Refresh'}</button></div></section>
  <section className="panel automationPanel">
   <div className="simpleStats automationStats progressStats">
    <article><small><ArrowUpRight size={16}/> Total paper P&amp;L</small><strong aria-live="polite" className={`pnlValue ${totalPnl>0?'positive':totalPnl<0?'negative':'neutral'} ${pnlPulse!=='none'?`pnlPulse-${pnlPulse}`:''}`}>{state?money(totalPnl):'Loading…'}</strong></article>
    <article><small>Realized P&amp;L</small><strong className={`pnlValue ${realizedPnl>0?'positive':realizedPnl<0?'negative':'neutral'}`}>{state?money(realizedPnl):'Loading…'}</strong></article>
    <article><small>Open P&amp;L</small><strong className={`pnlValue ${openPnl>0?'positive':openPnl<0?'negative':'neutral'}`}>{state?money(openPnl):'Loading…'}</strong></article>
    <article><small><Wallet size={16}/> Paper balance</small><strong>{state?money(state.balance):'Loading…'}</strong></article>
   </div>
   <div className="workspaceGrid"><div className="workspaceMain"><section className="tradeProgress" aria-label="Account summary"><div className="panelTitle"><h3><Activity size={18}/> Account snapshot</h3><span className="subtleTag">PAPER</span></div><div className="accountSnapshot"><div><small>Open positions</small><strong>{state?state.positions.length:'--'}</strong></div><div><small>Closed trades</small><strong>{state?state.trades.length:'--'}</strong></div><div><small>Starting balance</small><strong>{state?money(state.starting_balance):'--'}</strong></div></div></section><section className="dailyRiskProgress" aria-label="Daily paper risk progress">
    <div className="riskProgressHeading"><span>Daily risk used</span><strong>{dailyRisk?`${money(dailyRiskUsed)} / ${money(dailyRiskLimit)}`:'Loading…'}</strong></div>
    <div className={`riskProgressTrack ${riskOverBudget?'overBudget':''}`} role="meter" aria-label="Daily risk usage; paper automation is off" aria-valuemin={0} aria-valuemax={dailyRiskLimit||1} aria-valuenow={Math.min(dailyRiskUsed,dailyRiskLimit||1)} aria-valuetext={dailyRisk?`${money(dailyRiskUsed)} used of ${money(dailyRiskLimit)}${riskOverBudget?', over budget':''}`:'Loading'}>
     <span style={{width:`${dailyRiskPercent}%`}}/>
    </div>
   </section>
   <section className="tradeProgress" aria-label="Recent paper trade progress">
    <div className="panelTitle"><h3><Activity size={18}/> Recent activity</h3><span>Last 8 events</span></div><p className="activityLogHint">Closed trade results and P&amp;L changes observed this session. Changes include unrealized P&amp;L and are not additional trade results.</p>
    {!state?<p className="empty">Loading paper activity…</p>:activity.length===0?<div className="activityEmpty"><div><Activity size={25}/></div><h4>Your next chapter starts here</h4><p>Your trades and observed profit or loss changes will appear here. P&L changes are logged during this session.</p><span>Automatic updates every 15 seconds</span></div>:<div className="tradeActivityList">{activity.map(item=><article className={`tradeActivityItem ${item.kind}`} key={item.id}>
     <span className="activityDot" aria-hidden="true"/>
     <div className="activityDetails"><strong>{item.pair} · {item.side}</strong><small>{item.id.startsWith('pnl-')?'Observed P&L change (includes open positions)':item.kind==='open'?'Open position':item.kind==='profit'?'Closed in profit':item.kind==='loss'?'Closed at a loss':'Closed'} · {showDate(item.time)}</small></div>
     <strong className="activityPnl">{item.pnl===null?'Quote unavailable':(item.pnl>0?'+':item.pnl<0?'\u2212':'')+money(Math.abs(item.pnl))}</strong>
    </article>)}</div>}
   </section>
   </div><aside className="workspaceAside"><div className="panelTitle"><h3><SlidersHorizontal size={18}/> Paper preferences</h3></div><p className="settingsDescription">Set a reference amount for your simulated trades.</p><form className="allocationForm" onSubmit={applyTradeAmount}><label className="automationAmount" htmlFor="paper-trade-amount">Amount to allocate per paper trade (USD)
    <input id="paper-trade-amount" type="number" min="0.01" max="100000" step="0.01" required aria-invalid={!amountValid} aria-describedby="amount-help" value={tradeAmount} onChange={e=>{
     setTradeAmount(e.target.value);setAmountApplied(false);
    }}/>
   </label>
   <small id="amount-help" className={amountValid?'amountHelp':'amountHelp invalid'}>{!amountValid?'Enter $0.01 to $100,000 with up to two decimal places.':amountChanged?'Unsaved changes. Click Apply changes to save.':'Saved in this browser. No trade is placed.'}</small><button className="primary applyAmount" type="submit" disabled={!amountValid||!amountChanged}>Apply changes <ArrowRight size={16}/></button><small className="amountHelp">Saved allocation: {money(Number(savedTradeAmount))} per paper trade.</small>{amountApplied&&<p role="status" className="allocationConfirmation">New amount saved. No trade was placed.</p>}</form><div className="paperSafety"><ShieldCheck size={22}/><b>A space to practice</b><p>Automation is off. All balances and activity are simulated, with no live funds connected.</p></div></aside></div>
  </section>
  {state&&<TradingTerminal quotes={state.quotes} positions={state.positions} trades={state.trades} feed={state.feed_type} load={loadTerminal}/>}
  <footer>Paper-only settings · Simulated balance is not real money</footer>
 </main>;
}
createRoot(document.getElementById('root')!).render(<AccountWorkspace paper={<App/>}/>);
