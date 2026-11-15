import React, {useCallback,useEffect,useState} from 'react';
import {createRoot} from 'react-dom/client';
import './style.css';

const API=(import.meta.env.VITE_API_URL||'').trim().replace(/\/$/,'') ||
  (['localhost','127.0.0.1'].includes(location.hostname)?'http://127.0.0.1:8001':'');
const KEY='playgo_owner_session';
type Quote={bid:number;ask:number;pip:number;spread:number};
type PaperState={revision:number;balance:number;starting_balance:number;paused:boolean;feed_type:string;ticks:number;last_cycle_at:string|null;quotes:Record<string,Quote>;positions:unknown[];trades:unknown[];logs:{id:string;time:string;agent:string;message:string}[];risk_lock_reason:string|null;loss_streak:number};
type Order={client_order_id:string;status:string;request:{pair:string;side:string;units:number};fill:unknown;created_at:string};
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
 const logoutLocal=useCallback(()=>{sessionStorage.removeItem(KEY);setToken('');setState(null);setAccount(null);setOrders([]);setPassword('')},[]);
 const refresh=useCallback(async(t=token)=>{
  if(!t||!API)return;
  try{
   const [a,s]=await Promise.all([request('/api/identity/me/paper-account',t),request('/api/state',t)]);
   setAccount(a);setState(s.state);setError('');
  }catch(e){if((e as Error).message==='SESSION_EXPIRED')logoutLocal();else setError((e as Error).message)}
 },[token,logoutLocal]);
 useEffect(()=>{if(!token)return;void refresh();const timer=setInterval(()=>void refresh(),15000);return()=>clearInterval(timer)},[token,refresh]);
 async function login(e:React.FormEvent){e.preventDefault();setBusy(true);setError('');
  try{const d=await request('/api/identity/login','','POST',{username,password});if(typeof d.access_token!=='string')throw Error('Missing session token');sessionStorage.setItem(KEY,d.access_token);setToken(d.access_token);setPassword('')}
  catch(e){setError((e as Error).message)}finally{setBusy(false)}
 }
 async function logout(){setBusy(true);try{await request('/api/identity/logout',token,'POST')}catch(e){setError('Server logout not confirmed: '+(e as Error).message)}finally{logoutLocal();setBusy(false)}}
 async function changeState(paused:boolean){if(!state)return;setBusy(true);setError('');try{const d=await request('/api/state/control',token,'POST',{expected_revision:state.revision,paused});setState(d.state);setMessage('Paper engine '+(paused?'paused':'enabled'))}catch(e){setError((e as Error).message);await refresh()}finally{setBusy(false)}}
 async function cycle(){if(!state)return;setBusy(true);setError('');try{const d=await request('/api/auto-cycle',token,'POST',{expected_revision:state.revision});setState(d.state);setMessage('Synthetic observation completed — no order executed')}catch(e){setError((e as Error).message);await refresh()}finally{setBusy(false)}}
 async function order(e:React.FormEvent){e.preventDefault();if(!state)return;const q=state.quotes[pair];if(!q){setError('Quote unavailable');return}
  setBusy(true);setError('');try{const id='web-'+crypto.randomUUID();const d=await request('/api/demo/orders',token,'POST',{client_order_id:id,pair,side,units,bid:String(q.bid),ask:String(q.ask),slippage_pips:'0.2'});setOrders(v=>[d,...v]);setMessage('DEMO order '+d.status+' — not a live broker trade')}catch(e){setError((e as Error).message)}finally{setBusy(false)}
 }
 const money=(v:number)=>'$'+v.toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2});
 if(!API)return <main className="simpleApp"><section className="panel"><h2>Backend URL not configured</h2><p>Set VITE_API_URL to the PostgreSQL FastAPI origin.</p></section></main>;
 if(!token)return <main className="simpleApp"><header className="simpleHeader"><div className="brand"><div className="logo">P</div><h1>PlayGo AI Trading</h1></div><span className="pill">PAPER ONLY</span></header><section className="panel" style={{maxWidth:460,margin:'70px auto',padding:28}}><h2>Owner sign in</h2><p>Supabase PostgreSQL · Private owner access</p><form onSubmit={login} style={{display:'grid',gap:16,marginTop:20}}><label>Username<input required autoComplete="username" value={username} onChange={e=>setUsername(e.target.value)}/></label><label>Password<input required type="password" autoComplete="current-password" value={password} onChange={e=>setPassword(e.target.value)}/></label><button className="primary" disabled={busy}>{busy?'Signing in…':'Sign in'}</button></form>{error&&<p className="error" role="alert">{error}</p>}<small>No public registration. Demo trading only.</small></section></main>;
 return <main className="simpleApp"><header className="simpleHeader"><div className="brand"><div className="logo">P</div><div><h1>PlayGo AI Trading</h1><small>POSTGRESQL PAPER ACCOUNT</small></div></div><div className="headerRight"><span className="pill">PAPER ONLY</span><button className="secondary" disabled={busy} onClick={logout}>Sign out</button></div></header>
 <div className="viewContent"><div className="viewHeading"><div><h2>Owner dashboard</h2><p>{account?.role||'OWNER'} · {account?.mode||'PAPER'} · Supabase-backed</p></div><button className="secondary" onClick={()=>void refresh()} disabled={busy}>Refresh</button></div>
 {error&&<div className="error" role="alert">{error}</div>}{message&&<p role="status">{message}</p>}
 {!state?<section className="panel"><p>Loading authoritative paper state…</p></section>:<>
 <div className="simpleStats"><article><small>Paper balance</small><strong>{money(state.balance)}</strong></article><article><small>Initial balance</small><strong>{money(state.starting_balance)}</strong></article><article><small>Revision</small><strong>{state.revision}</strong></article><article><small>Observations</small><strong>{state.ticks}</strong></article></div>
 <section className="panel"><div className="panelTitle"><h3>Paper engine</h3><span className="pill">{state.paused?'PAUSED':'ENABLED'}</span></div><p>Feed: {state.feed_type}. Enabling the engine does not place trades. Cycles observe synthetic prices only.</p>{state.risk_lock_reason&&<p className="error">Risk lock: {state.risk_lock_reason}</p>}<div className="simpleActions"><button className="primary" disabled={busy} onClick={()=>changeState(!state.paused)}>{state.paused?'Enable paper engine':'Pause paper engine'}</button><button className="secondary" disabled={busy} onClick={cycle}>Run synthetic cycle</button></div><small>Last cycle: {state.last_cycle_at||'Never'}</small></section>
 <section className="panel"><div className="panelTitle"><h3>Synthetic market quotes</h3><span>{Object.keys(state.quotes).length} pairs</span></div><div className="simpleTableHead"><span>Pair</span><span>Bid</span><span>Ask</span></div>{Object.entries(state.quotes).map(([name,q])=><div className="simpleTableRow" key={name}><b>{name}</b><span>{q.bid}</span><span>{q.ask}</span></div>)}</section>
 <section className="panel"><div className="panelTitle"><h3>Submit simulated DEMO order</h3><span className="pill">NO LIVE TRADING</span></div><p>Uses the currently displayed synthetic quote. Fills are deterministic and persisted separately from paper account positions.</p><form onSubmit={order} className="modalFields"><label>Pair<select value={pair} onChange={e=>setPair(e.target.value)}>{Object.keys(state.quotes).map(x=><option key={x}>{x}</option>)}</select></label><label>Direction<select value={side} onChange={e=>setSide(e.target.value)}><option>BUY</option><option>SELL</option></select></label><label>Units<input type="number" min="1" max="100000" required value={units} onChange={e=>setUnits(Number(e.target.value))}/></label><button className="primary" disabled={busy||!Number.isSafeInteger(units)||units<1||units>100000}>Submit DEMO order</button></form>{orders.map(o=><div className="simpleItem" key={o.client_order_id}><b>{o.request.pair} · {o.request.side} · {o.request.units} units</b><span>{o.status}</span></div>)}</section>
 <section className="panel"><div className="panelTitle"><h3>Recent state events</h3></div>{state.logs.length===0?<p className="empty">No events yet</p>:state.logs.slice(0,15).map(l=><div className="simpleItem" key={l.id}><div><b>{l.agent}</b><small>{l.message}</small></div><small>{l.time}</small></div>)}</section>
 </>}</div><footer>PlayGo Tanzania · Paper only · No live brokerage connection</footer></main>
}
createRoot(document.getElementById('root')!).render(<App/>);
