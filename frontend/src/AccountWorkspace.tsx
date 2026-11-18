import React,{useCallback,useEffect,useState} from 'react';
import {Activity,Wallet,ShieldCheck,RefreshCw,ExternalLink,LogOut} from 'lucide-react';
import './real-account.css';
import DerivMarketPanel from './DerivMarketPanel';
const API=(import.meta.env.VITE_API_URL||'https://playgo-ai-trading-api.vercel.app').trim().replace(/\/$/,'');
const KEY='playgo_owner_session';
const HANDOFF_KEY='playgo_deriv_signin_handoff';
const randomSecret=()=>btoa(String.fromCharCode(...crypto.getRandomValues(new Uint8Array(32)))).replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/,'');
type Account={account_id:string;currency:string;balance:string|null;account_type:'real'|'demo'};
type Snapshot={connected:boolean;reason?:string;accounts:Account[];observed_at?:string};
type DemoBotState={execution:'DEMO_ONLY';strategy:string;symbol:string;contract_type:string;duration_minutes:number;stake:string;daily_stake_limit:string;account_id:string;running:boolean;status:string;daily_stake:string;active_contract_id:string|null;last_trade:{contract_id:string;side:string;stake:string;created_at:string;status:string}|null;last_cycle_at:string|null;last_error:string|null};
function balanceLabel(account:Account){
 if(account.balance===null)return 'Unavailable';
 const value=Number(account.balance);
 if(!Number.isFinite(value))return 'Unavailable';
 return `${account.currency} ${value.toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:8})}`;
}
export default function AccountWorkspace({paper}:{paper:React.ReactNode}){
 const [oauthBusy,setOauthBusy]=useState(false),[selectedId,setSelectedId]=useState('');
 const [token,setToken]=useState(()=>sessionStorage.getItem(KEY)||'');
 const [username,setUsername]=useState('playgo_admin'),[password,setPassword]=useState('');
 const [view,setView]=useState<'real'|'paper'>('real');
 const [data,setData]=useState<Snapshot|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false),[signingIn,setSigningIn]=useState(false),[refresh,setRefresh]=useState(0);
 const [botState,setBotState]=useState<DemoBotState|null>(null),[botBusy,setBotBusy]=useState(false),[botError,setBotError]=useState('');
 const selected=data?.accounts.find(account=>account.account_id===selectedId)??data?.accounts.find(account=>account.account_type==='real')??data?.accounts[0];
 const derivSession=token.startsWith('deriv_');
 const loadMarkets=useCallback(async(path:string)=>{
  const headers:HeadersInit=token?{Authorization:'Bearer '+token}:{};
  const response=await fetch(API+path,{cache:'no-store',headers});
  const body=await response.json().catch(()=>({}));
  if(!response.ok)throw Error(typeof body.detail==='string'?body.detail:'Unable to load Deriv market data.');
  return body;
 },[token]);
 async function signInWithDeriv(){
  setError('');
  const popup=window.open('about:blank','playgo-deriv-signin','popup,width=520,height=720');
  if(!popup){setError('Allow popups for PlayGo, then try signing in again.');return}
  setOauthBusy(true);
  try{
   const handoffId=randomSecret(),verifier=randomSecret();
   const hash=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(verifier));
   const challenge=btoa(String.fromCharCode(...new Uint8Array(hash))).replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/,'');
   sessionStorage.setItem(HANDOFF_KEY,JSON.stringify({handoffId,verifier,createdAt:Date.now()}));
   const params=new URLSearchParams({origin:window.location.origin,handoff_id:handoffId,handoff_challenge:challenge});
   popup.opener=null;
   const authUrl=new URL('/api/deriv/oauth/signin',API||window.location.origin);
   authUrl.search=params.toString();
   popup.location.href=authUrl.toString();
   const deadline=Date.now()+600000;
   let popupClosedAt=0;
   while(Date.now()<deadline){
    const response=await fetch(API+'/api/deriv/oauth/complete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({handoff_id:handoffId,verifier})});
    const body=await response.json();
    if(response.status===202){
     if(popup.closed){
      if(!popupClosedAt)popupClosedAt=Date.now();
      if(Date.now()-popupClosedAt>8000)throw Error('Sign-in was not completed. Please try again.');
     }
     await new Promise(resolve=>window.setTimeout(resolve,750));
     continue;
    }
    if(!response.ok)throw Error(typeof body.detail==='string'?body.detail:'Unable to complete sign-in. Please try again.');
    if(typeof body.session_token!=='string'||!/^deriv_[A-Za-z0-9_-]{64}$/.test(body.session_token))throw Error('Invalid sign-in response.');
    sessionStorage.setItem(KEY,body.session_token);setToken(body.session_token);setSelectedId('');setError('');
    return;
   }
   throw Error('Sign-in timed out. Please try again.');
  }catch(e){setError((e as Error).message)}
  finally{sessionStorage.removeItem(HANDOFF_KEY);if(!popup.closed)popup.close();setOauthBusy(false)}
 }
 useEffect(()=>{
  if(!token||view!=='real'||oauthBusy)return;
  let active=true,inFlight=false;const controller=new AbortController();
  async function load(){
   if(inFlight)return;inFlight=true;setBusy(true);
   try{
    const response=await fetch(API+'/api/deriv/accounts',{cache:'no-store',headers:{Authorization:'Bearer '+token},signal:controller.signal});
    const body=await response.json();
    if(!active)return;
    if(response.status===401){sessionStorage.removeItem(KEY);setToken('');setData(null);setError('Your PlayGo session expired. Please sign in again.');return;}
    if(!response.ok)throw Error(typeof body.detail==='string'?body.detail:'Unable to load Deriv balances.');
    if(typeof body.connected!=='boolean'||!Array.isArray(body.accounts))throw Error('Invalid balance response.');
    setData(body as Snapshot);setError('');
   }catch(e){if(active){setData(null);setError((e as Error).message==='Failed to fetch'?'Cannot reach the balance service. Please retry.':(e as Error).message)}}
   finally{inFlight=false;if(active)setBusy(false)}
  }
  void load();const timer=window.setInterval(()=>void load(),30000);
  return()=>{active=false;controller.abort();window.clearInterval(timer)};
 },[token,view,refresh,oauthBusy]);
 useEffect(()=>{
  if(!token||!derivSession||selected?.account_type!=='demo'){setBotState(null);setBotError('');return}
  let active=true;setBotError('');
  fetch(API+'/api/deriv/demo-bot?account_id='+encodeURIComponent(selected.account_id),{cache:'no-store',headers:{Authorization:'Bearer '+token}})
   .then(async response=>{const body=await response.json();if(!response.ok)throw Error(typeof body.detail==='string'?body.detail:'Unable to load demo bot status.');return body as DemoBotState})
   .then(state=>{if(active)setBotState(state)})
   .catch(e=>{if(active){setBotState(null);setBotError((e as Error).message)}})
  return()=>{active=false}
 },[token,derivSession,selected?.account_id,selected?.account_type,refresh]);
 async function botAction(action:'start'|'stop'){
  if(!selected||selected.account_type!=='demo')return;
  setBotBusy(true);setBotError('');
  try{
   const response=await fetch(API+'/api/deriv/demo-bot/'+action,{method:'POST',headers:{'Authorization':'Bearer '+token,'Content-Type':'application/json'},body:JSON.stringify({account_id:selected.account_id})});
   const body=await response.json();
   if(typeof body.execution==='string')setBotState(body as DemoBotState);
   if(!response.ok)throw Error(typeof body.detail==='string'?body.detail:typeof body.last_error==='string'?body.last_error:'Unable to '+action+' the demo bot.');
  }catch(e){setBotError((e as Error).message)}
  finally{setBotBusy(false)}
 }
 async function resolveBot(){
  if(!selected||selected.account_type!=='demo')return;
  setBotBusy(true);setBotError('');
  try{
   const response=await fetch(API+'/api/deriv/demo-bot/resolve',{method:'POST',headers:{'Authorization':'Bearer '+token,'Content-Type':'application/json'},body:JSON.stringify({account_id:selected.account_id,confirmed_account_review:true})});
   const body=await response.json();
   if(typeof body.execution==='string')setBotState(body as DemoBotState);
   if(!response.ok)throw Error(typeof body.detail==='string'?body.detail:'Unable to resolve demo bot status.');
  }catch(e){setBotError((e as Error).message)}
  finally{setBotBusy(false)}
 }
 useEffect(()=>{
  if(!token||!derivSession||!selected||selected.account_type!=='demo'||!botState?.running)return;
  const accountId=selected.account_id;
  let active=true,inFlight=false;
  async function cycle(){
   if(inFlight)return;inFlight=true;
   try{
    const response=await fetch(API+'/api/deriv/demo-bot/cycle',{method:'POST',headers:{'Authorization':'Bearer '+token,'Content-Type':'application/json'},body:JSON.stringify({account_id:accountId})});
    const body=await response.json();
    if(active&&typeof body.execution==='string')setBotState(body as DemoBotState);
    if(response.status===401){sessionStorage.removeItem(KEY);setToken('');setData(null);setError('Your Deriv session expired. Please sign in again.')}
    if(!response.ok)throw Error(typeof body.last_error==='string'?body.last_error:typeof body.detail==='string'?body.detail:'Demo bot cycle failed.');
    if(active)setBotError('');
   }catch(e){if(active)setBotError((e as Error).message)}
   finally{inFlight=false}
  }
  void cycle();const timer=window.setInterval(()=>void cycle(),30000);
  return()=>{active=false;window.clearInterval(timer)}
 },[token,derivSession,selected?.account_id,selected?.account_type,botState?.running]);
 async function login(e:React.FormEvent){
  e.preventDefault();setSigningIn(true);setError('');
  try{
   const r=await fetch(API+'/api/identity/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username,password})});const body=await r.json();
   if(!r.ok)throw Error(typeof body.detail==='string'?body.detail:'Sign-in failed.');
   if(typeof body.access_token!=='string')throw Error('Invalid sign-in response.');
   sessionStorage.setItem(KEY,body.access_token);setToken(body.access_token);setPassword('');
  }catch(e){setError((e as Error).message)}finally{setSigningIn(false)}
 }
 async function logout(){
  setOauthBusy(false);
  setBusy(true);setError('');
  try{const r=await fetch(API+(derivSession?'/api/deriv/session/logout':'/api/identity/logout'),{method:'POST',headers:{Authorization:'Bearer '+token}});if(!r.ok&&r.status!==401)throw Error('Unable to revoke the session. Please retry sign-out.');sessionStorage.removeItem(KEY);setToken('');setData(null);setPassword('')}
  catch(e){setError((e as Error).message)}finally{setBusy(false)}
 }
 if(view==='paper')return <><nav className="accountSwitch"><button onClick={()=>{setView('real');setToken(sessionStorage.getItem(KEY)||'')}}>Return to Deriv accounts</button><span>Paper simulation is separate from your real funds.</span></nav>{paper}</>;
 return (
  <main className="realWorkspace">
   <header>
    <div className="realBrand"><Activity size={25}/><div><b>PlayGo<span>.</span></b><small>DERIV ACCOUNT OVERVIEW</small></div></div>
    <div className="realHeaderActions">
     <span className={`realBadge ${selected?.account_type==='demo'?'demoBadge':''}`}><ShieldCheck size={13}/>{selected?selected.account_type.toUpperCase()+' ACCOUNT':'READ ONLY'}</span>
     {token&&<button disabled={busy} onClick={()=>void logout()}><LogOut size={15}/> Sign out</button>}
    </div>
   </header>
   {data?.connected&&selected&&<label className="derivAccountSelector">Selected Deriv account<select value={selected.account_id} onChange={e=>setSelectedId(e.target.value)}>{data.accounts.map(account=><option value={account.account_id} key={account.account_id}>{account.account_type==='demo'?'Demo':'Real'} / {account.currency} / {account.account_id}</option>)}</select></label>}
   <section className="realHero"><div><small>YOUR CONNECTED ACCOUNT</small><h1>Your Deriv account<span>.</span></h1><p>Choose your demo or real Options account.</p></div>{token&&<button disabled={busy} onClick={()=>setRefresh(v=>v+1)}><RefreshCw size={16}/>{busy?'Refreshing...':'Refresh'}</button>}</section>
   {error&&<p className="realError" role="alert">{error}</p>}
   <DerivMarketPanel load={loadMarkets} accountId={data?.connected?selected?.account_id:undefined} accountType={selected?.account_type}/>
   {oauthBusy?<p role="status" className="realEmpty">Completing Deriv sign-in...</p>:!token?<section className="realLogin"><h2>Welcome to PlayGo</h2><p>Sign in with Deriv to view your demo and real accounts.</p><button className="realPrimary derivSignIn" disabled={oauthBusy} onClick={signInWithDeriv}>{oauthBusy?'Waiting for Deriv...':'Sign in with Deriv'}<ExternalLink size={16}/></button><small className="derivLoginHelp">Sign in securely on Deriv, then return here automatically. Your Deriv password stays with Deriv.</small><details className="ownerLogin"><summary>PlayGo owner sign-in</summary><form onSubmit={login}><label>Username<input required autoComplete="username" value={username} onChange={e=>setUsername(e.target.value)}/></label><label>Password<input required type="password" autoComplete="current-password" value={password} onChange={e=>setPassword(e.target.value)}/></label><button disabled={signingIn}>{signingIn?'Signing in...':'Sign in as owner'}</button></form></details></section>:data?.connected?<><div className="realStatus"><span>Connected to Deriv</span><small>{data.observed_at?'Last updated '+new Date(data.observed_at).toLocaleString():''}</small></div>{selected?<><section className="realBalances"><article className={selected.account_type==='demo'?'demoAccount':''}><div><Wallet size={20}/><span>{selected.account_type==='demo'?'DEMO ACCOUNT / VIRTUAL FUNDS':'REAL ACCOUNT / REAL FUNDS'}</span></div><small>{selected.account_id}</small><strong>{balanceLabel(selected)}</strong><span>{selected.account_type==='demo'?'Deriv demo balance':'Deriv real balance'} / {selected.currency}</span></article></section>{derivSession&&selected.account_type==='demo'&&<section className="demoBotPanel" aria-label="Deriv demo bot"><div className="demoBotHeading"><div><h2>Deriv demo bot</h2><p>EMA 9/21 · EUR/USD · 5-minute Rise/Fall</p></div><span className={botState?.running?'botRunning':'botStopped'}>{botState?.status?.replace(/_/g,' ')||'checking'}</span></div><div className="demoBotLimits"><span>Stake per contract <b>USD 2.00</b></span><span>Daily stake cap <b>USD 5.00</b></span><span>Used today <b>USD {Number(botState?.daily_stake||0).toFixed(2)}</b></span></div>{botState?.last_trade&&<small className="demoBotTrade">Last contract: {botState.last_trade.side==='BUY'?'Rise':'Fall'} · {botState.last_trade.contract_id} · {botState.last_trade.status}</small>}{botState?.last_error&&<p className="realError" role="alert">{botState.last_error}</p>}{botError&&<p className="realError" role="alert">{botError}</p>}{botState?.status==='needs_review'&&<p className="demoBotWarning" role="alert">The outcome of a trade request is uncertain. Check your Deriv demo account before attempting another start.</p>}<div className="demoBotActions">{botState?.status==='needs_review'?<button className="botStopButton" disabled={botBusy} onClick={()=>void resolveBot()}>{botBusy?'Resolving...':'I checked Deriv — acknowledge'}</button>:botState?.running?<button className="botStopButton" disabled={botBusy} onClick={()=>void botAction('stop')}>{botBusy?'Stopping...':'Stop bot'}</button>:<button className="realPrimary" disabled={botBusy||!botState} onClick={()=>void botAction('start')}>{botBusy?'Starting...':'Initiate demo bot'}</button>}</div>{!botState&&<small role="status">Loading bot status...</small>}</section>}</>:<section className="realEmpty"><Wallet size={30}/><h2>No Options accounts returned</h2><p>Deriv returned no demo or real Options accounts for this sign-in. Wallets and MT5 accounts are not included.</p></section>}</>:busy&&!data?<p role="status" className="realEmpty">Checking your Deriv connection...</p>:<section className="realEmpty"><div className="realConnectIcon"><Wallet size={30}/></div><h2>Sign in with Deriv</h2><p>Authorize Deriv to view your accounts and see whether you are using demo or real funds.</p><button className="realPrimary" disabled={oauthBusy} onClick={signInWithDeriv}>{oauthBusy?'Waiting for Deriv...':'Sign in with Deriv'} <ExternalLink size={16}/></button></section>}
   <footer><span>PlayGo / Deriv account overview</span>{token&&<button disabled={oauthBusy} onClick={signInWithDeriv}>Switch Deriv sign-in</button>}{!derivSession&&<button onClick={()=>setView('paper')}>Open paper simulation</button>}</footer>
  </main>
 );
}
