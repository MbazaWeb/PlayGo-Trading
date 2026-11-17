import React, {useCallback,useEffect,useState} from 'react';
import {createRoot} from 'react-dom/client';
import './style.css';
import AccountWorkspace from './AccountWorkspace';

const API=(import.meta.env.VITE_API_URL||'').trim().replace(/\/$/,'') ||
  (['localhost','127.0.0.1'].includes(location.hostname)?'http://127.0.0.1:8001':'');
const KEY='playgo_owner_session';
type Quote={bid:number;ask:number;pip:number;spread:number};
type Position={id:string;pair:string;side:"BUY"|"SELL";units:number;entry_price:string;stop_loss:string;opened_at:string;status:string;exit_price?:string;pnl?:string;closed_at?:string};
type Reconciliation={consistent:boolean;balances_cents:Record<string,number>;issues:string[]};
type PaperState={revision:number;balance:number;starting_balance:number;paused:boolean;feed_type:string;ticks:number;last_cycle_at:string|null;quotes:Record<string,Quote>;positions:Position[];trades:Position[];logs:{id:string;time:string;agent:string;message:string}[];risk_lock_reason:string|null;loss_streak:number};
type Order={client_order_id:string;status:string;request:{pair:string;side:string;units:number;bid:string;ask:string;slippage_pips:string};fill:Record<string,unknown>|null;created_at:string;updated_at:string};
type OrderPage={mode:string;total:number;limit:number;offset:number;orders:Order[]};
type Analytics={mode:string;feed_type:string;paper:{balance:number;starting_balance:number;revision:number;observations:number;paused:boolean;risk_lock_reason:string|null;open_positions:number;closed_trade_records:number};demo_orders:{total:number;by_status:Record<string,number>;by_pair:Record<string,number>};performance:{realized_pnl:null;unrealized_pnl:null;win_rate:null;max_drawdown:null;equity_curve:null;availability:string};disclaimer:string};
const showDate=(value:string)=>{const date=new Date(value);return Number.isNaN(date.getTime())?value:date.toLocaleString()};
async function request(path:string,token='',method='GET',body?:unknown){
 const r=await fetch(API+path,{method,cache:'no-store',headers:{...(token?{Authorization:'Bearer '+token}:{}),...(body!==undefined?{'Content-Type':'application/json'}:{})},body:body===undefined?undefined:JSON.stringify(body)});
 const data=await r.json().catch(()=>({}));
 if(!r.ok)throw new Error(r.status===401?'SESSION_EXPIRED':typeof data.detail==='string'?data.detail:'HTTP '+r.status);
 return data;
}
function App(){
 const [token,setToken]=useState(()=>sessionStorage.getItem(KEY)||'');
 const [username,setUsername]=useState('playgo_admin'),[password,setPassword]=useState('');
 const [state,setState]=useState<PaperState|null>(null),[account,setAccount]=useState<{role:string;mode:string}|null>(null);
 const [orders,setOrders]=useState<Order[]>([]),[pair,setPair]=useState('EURUSD'),[side,setSide]=useState('BUY'),[units,setUnits]=useState(1000);
 const [busy,setBusy]=useState(false),[error,setError]=useState(''),[message,setMessage]=useState('');
 const [tab,setTab]=useState<'dashboard'|'positions'|'history'|'analytics'>('dashboard');
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
 <nav className="historyNav" aria-label="Dashboard sections"><button type="button" className={tab==='dashboard'?'selected':''} onClick={()=>setTab('dashboard')}>Dashboard</button><button type="button" className={tab==='positions'?'selected':''} onClick={()=>setTab('positions')}>Positions</button><button type="button" className={tab==='history'?'selected':''} onClick={()=>setTab('history')}>Order history</button><button type="button" className={tab==='analytics'?'selected':''} onClick={()=>setTab('analytics')}>Analytics</button></nav>
 {tab==='positions'?<div className="viewContent"><div className="viewHeading"><div><h2>PAPER positions</h2><p>Synthetic prices · No broker execution</p></div><button className="secondary" disabled={busy} onClick={()=>{void refresh();void loadReconciliation()}}>Refresh positions</button></div>
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
createRoot(document.getElementById('root')!).render(<AccountWorkspace paper={<App/>}/>);
