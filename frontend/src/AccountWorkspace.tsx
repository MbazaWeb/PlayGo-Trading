import React,{useEffect,useState} from 'react';
import {Activity,Wallet,ShieldCheck,RefreshCw,ExternalLink,LogOut} from 'lucide-react';
import './real-account.css';
const API=(import.meta.env.VITE_API_URL||'https://playgo-ai-trading-api.vercel.app').trim().replace(/\/$/,'');
const KEY='playgo_owner_session';
type Account={account_id:string;currency:string;balance:string|null;account_type:'real'};
type Snapshot={connected:boolean;reason?:string;accounts:Account[];observed_at?:string};
function balanceLabel(account:Account){
 if(account.balance===null)return 'Unavailable';
 const value=Number(account.balance);
 if(!Number.isFinite(value))return 'Unavailable';
 return `${account.currency} ${value.toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:8})}`;
}
export default function AccountWorkspace({paper}:{paper:React.ReactNode}){
 const [token,setToken]=useState(()=>sessionStorage.getItem(KEY)||'');
 const [username,setUsername]=useState('playgo_admin'),[password,setPassword]=useState('');
 const [view,setView]=useState<'real'|'paper'>('real');
 const [data,setData]=useState<Snapshot|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false),[signingIn,setSigningIn]=useState(false),[refresh,setRefresh]=useState(0);
 useEffect(()=>{
  if(!token||view!=='real')return;
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
 },[token,view,refresh]);
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
  setBusy(true);setError('');
  try{const r=await fetch(API+'/api/identity/logout',{method:'POST',headers:{Authorization:'Bearer '+token}});if(!r.ok&&r.status!==401)throw Error('Unable to revoke the session. Please retry sign-out.');sessionStorage.removeItem(KEY);setToken('');setData(null);setPassword('')}
  catch(e){setError((e as Error).message)}finally{setBusy(false)}
 }
 if(view==='paper')return <><nav className="accountSwitch"><button onClick={()=>{setView('real');setToken(sessionStorage.getItem(KEY)||'')}}>Return to real Deriv balance</button><span>Paper simulation is separate from your real funds.</span></nav>{paper}</>;
 return <main className="realWorkspace"><header><div className="realBrand"><Activity size={25}/><div><b>PlayGo<span>.</span></b><small>DERIV ACCOUNT OVERVIEW</small></div></div><div className="realHeaderActions"><span className="realBadge"><ShieldCheck size={13}/> READ ONLY</span>{token&&<button disabled={busy} onClick={()=>void logout()}><LogOut size={15}/> Sign out</button>}</div></header>
 <section className="realHero"><div><small>YOUR CONNECTED ACCOUNT</small><h1>Your real Deriv balance<span>.</span></h1><p>Actual Options account balances reported by Deriv.</p></div>{token&&<button disabled={busy} onClick={()=>setRefresh(v=>v+1)}><RefreshCw size={16}/>{busy?'Refreshing...':'Refresh'}</button>}</section>
 {error&&<p className="realError" role="alert">{error}</p>}
 {!token?<section className="realLogin"><h2>Sign in to PlayGo</h2><p>Then connect Deriv to view your real balance.</p><form onSubmit={login}><label>Username<input required autoComplete="username" value={username} onChange={e=>setUsername(e.target.value)}/></label><label>Password<input required type="password" autoComplete="current-password" value={password} onChange={e=>setPassword(e.target.value)}/></label><button className="realPrimary" disabled={signingIn}>{signingIn?'Signing in...':'Sign in'}</button></form></section>:data?.connected?<><div className="realStatus"><span>Connected to Deriv</span><small>{data.observed_at?'Last updated '+new Date(data.observed_at).toLocaleString():''}</small></div>{data.accounts.length?<section className="realBalances">{data.accounts.map(account=><article key={account.account_id}><div><Wallet size={20}/><span>REAL ACCOUNT</span></div><small>{account.account_id}</small><strong>{balanceLabel(account)}</strong><span>Balance / {account.currency}</span></article>)}</section>:<section className="realEmpty"><Wallet size={30}/><h2>No real Options accounts returned</h2><p>Deriv returned no real Options accounts for this connection. Demo funds, wallets, and MT5 balances are not included.</p></section>}<p className="realFootnote">Balances refresh every 30 seconds. Each account is shown in its own currency. No paper funds are included.</p></>:busy&&!data?<p role="status" className="realEmpty">Checking your Deriv connection...</p>:<section className="realEmpty"><div className="realConnectIcon"><Wallet size={30}/></div><h2>{data?.reason==='RECONNECT_REQUIRED'?'Reconnect your Deriv account':'Connect your Deriv account'}</h2><p>Your balance will appear after you authorize the connection. We will never substitute a simulated balance.</p><a className="realPrimary" href={API+'/deriv/connect'}>Connect Deriv <ExternalLink size={16}/></a></section>}
 <section className="realInfo"><ShieldCheck size={21}/><div><b>Balance viewing only</b><p>Deriv requires its trade permission to read Options balances. PlayGo only requests account data; it does not place trades or transfer funds. Previously connected? Reconnect once to authorize balance access.</p></div></section>
 <footer><span>PlayGo / Real account overview</span><button onClick={()=>setView('paper')}>Open paper simulation</button></footer>
 </main>;
}
