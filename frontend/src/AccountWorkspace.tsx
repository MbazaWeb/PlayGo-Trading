import React,{useEffect,useRef,useState} from 'react';
import {Activity,Wallet,ShieldCheck,RefreshCw,ExternalLink,LogOut} from 'lucide-react';
import './real-account.css';
const API=(import.meta.env.VITE_API_URL||'https://playgo-ai-trading-api.vercel.app').trim().replace(/\/$/,'');
const KEY='playgo_owner_session';
type Account={account_id:string;currency:string;balance:string|null;account_type:'real'|'demo'};
type Snapshot={connected:boolean;reason?:string;accounts:Account[];observed_at?:string};
function balanceLabel(account:Account){
 if(account.balance===null)return 'Unavailable';
 const value=Number(account.balance);
 if(!Number.isFinite(value))return 'Unavailable';
 return `${account.currency} ${value.toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:8})}`;
}
export default function AccountWorkspace({paper}:{paper:React.ReactNode}){
 const popup=useRef<Window|null>(null);
 const [oauthBusy,setOauthBusy]=useState(false),[selectedId,setSelectedId]=useState('');
 const [token,setToken]=useState(()=>sessionStorage.getItem(KEY)||'');
 const [username,setUsername]=useState('playgo_admin'),[password,setPassword]=useState('');
 const [view,setView]=useState<'real'|'paper'>('real');
 const [data,setData]=useState<Snapshot|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false),[signingIn,setSigningIn]=useState(false),[refresh,setRefresh]=useState(0);
 const selected=data?.accounts.find(account=>account.account_id===selectedId)??data?.accounts.find(account=>account.account_type==='real')??data?.accounts[0];
 const derivSession=token.startsWith('deriv_');
 function signInWithDeriv(){
  setError('');popup.current?.close();
  const opened=window.open(API+'/api/deriv/oauth/signin?origin='+encodeURIComponent(window.location.origin),'playgo-deriv-login','popup,width=520,height=740');
  if(!opened){setError('Allow popups for PlayGo, then click Sign in with Deriv again.');return;}
  popup.current=opened;setOauthBusy(true);
 }
 useEffect(()=>{
  function receive(event:MessageEvent){
   if(!popup.current||event.origin!==new URL(API).origin||event.source!==popup.current||!event.data||event.data.type!=='playgo-deriv-signin'||!/^deriv_[A-Za-z0-9_-]{64}$/.test(event.data.session_token))return;
   sessionStorage.setItem(KEY,event.data.session_token);setToken(event.data.session_token);setData(null);setSelectedId('');setView('real');setError('');setOauthBusy(false);popup.current?.close();popup.current=null;
  }
  window.addEventListener('message',receive);
  return()=>{window.removeEventListener('message',receive);popup.current?.close()};
 },[]);
 useEffect(()=>{
  if(!oauthBusy)return;
  const started=Date.now();let closedAt=0;
  const timer=window.setInterval(()=>{
   if(popup.current?.closed&&!closedAt)closedAt=Date.now();
   if(!popup.current||(closedAt>0&&Date.now()-closedAt>1500)||Date.now()-started>600000){setOauthBusy(false);popup.current?.close();popup.current=null;setError('Deriv sign-in was not completed. Please try again.');}
  },750);
  return()=>window.clearInterval(timer);
 },[oauthBusy]);
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
  popup.current?.close();popup.current=null;setOauthBusy(false);
  setBusy(true);setError('');
  try{const r=await fetch(API+(derivSession?'/api/deriv/session/logout':'/api/identity/logout'),{method:'POST',headers:{Authorization:'Bearer '+token}});if(!r.ok&&r.status!==401)throw Error('Unable to revoke the session. Please retry sign-out.');sessionStorage.removeItem(KEY);setToken('');setData(null);setPassword('')}
  catch(e){setError((e as Error).message)}finally{setBusy(false)}
 }
 if(view==='paper')return <><nav className="accountSwitch"><button onClick={()=>{setView('real');setToken(sessionStorage.getItem(KEY)||'')}}>Return to Deriv accounts</button><span>Paper simulation is separate from your real funds.</span></nav>{paper}</>;
 return <main className="realWorkspace"><header><div className="realBrand"><Activity size={25}/><div><b>PlayGo<span>.</span></b><small>DERIV ACCOUNT OVERVIEW</small></div></div><div className="realHeaderActions"><span className={`realBadge ${selected?.account_type==='demo'?'demoBadge':''}`}><ShieldCheck size={13}/>{selected?selected.account_type.toUpperCase()+' ACCOUNT':'READ ONLY'}</span>{token&&<button disabled={busy} onClick={()=>void logout()}><LogOut size={15}/> Sign out</button>}</div></header>
 <section className="realHero"><div><small>YOUR CONNECTED ACCOUNT</small><h1>Your Deriv account<span>.</span></h1><p>Choose your demo or real Options account.</p></div>{token&&<button disabled={busy} onClick={()=>setRefresh(v=>v+1)}><RefreshCw size={16}/>{busy?'Refreshing...':'Refresh'}</button>}</section>
 {error&&<p className="realError" role="alert">{error}</p>}
 {!token?<section className="realLogin"><h2>Welcome to PlayGo</h2><p>Sign in with Deriv to view your demo and real accounts.</p><button className="realPrimary derivSignIn" disabled={oauthBusy} onClick={signInWithDeriv}>{oauthBusy?'Waiting for Deriv...':'Sign in with Deriv'}<ExternalLink size={16}/></button><small className="derivLoginHelp">Deriv opens securely in a separate window. Your Deriv password stays with Deriv.</small><details className="ownerLogin"><summary>PlayGo owner sign-in</summary><form onSubmit={login}><label>Username<input required autoComplete="username" value={username} onChange={e=>setUsername(e.target.value)}/></label><label>Password<input required type="password" autoComplete="current-password" value={password} onChange={e=>setPassword(e.target.value)}/></label><button disabled={signingIn}>{signingIn?'Signing in...':'Sign in as owner'}</button></form></details></section>:data?.connected?<><div className="realStatus"><span>Connected to Deriv</span><small>{data.observed_at?'Last updated '+new Date(data.observed_at).toLocaleString():''}</small></div>{selected?<><label className="derivAccountSelector">Selected Deriv account<select value={selected.account_id} onChange={e=>setSelectedId(e.target.value)}>{data.accounts.map(account=><option value={account.account_id} key={account.account_id}>{account.account_type==='demo'?'Demo':'Real'} / {account.currency} / {account.account_id}</option>)}</select></label><section className="realBalances"><article className={selected.account_type==='demo'?'demoAccount':''}><div><Wallet size={20}/><span>{selected.account_type==='demo'?'DEMO ACCOUNT / VIRTUAL FUNDS':'REAL ACCOUNT / REAL FUNDS'}</span></div><small>{selected.account_id}</small><strong>{balanceLabel(selected)}</strong><span>{selected.account_type==='demo'?'Deriv demo balance':'Deriv real balance'} / {selected.currency}</span></article></section></>:<section className="realEmpty"><Wallet size={30}/><h2>No Options accounts returned</h2><p>Deriv returned no demo or real Options accounts for this sign-in. Wallets and MT5 accounts are not included.</p></section>}<p className="realFootnote">Balances refresh every 30 seconds. Demo funds are virtual; real funds belong to the selected real account. PlayGo paper simulation is separate.</p></>:busy&&!data?<p role="status" className="realEmpty">Checking your Deriv connection...</p>:<section className="realEmpty"><div className="realConnectIcon"><Wallet size={30}/></div><h2>Sign in with Deriv</h2><p>Authorize Deriv to view your accounts and see whether you are using demo or real funds.</p><button className="realPrimary" disabled={oauthBusy} onClick={signInWithDeriv}>{oauthBusy?'Waiting for Deriv...':'Sign in with Deriv'} <ExternalLink size={16}/></button></section>}

 <footer><span>PlayGo / Deriv account overview</span>{token&&<button disabled={oauthBusy} onClick={signInWithDeriv}>Switch Deriv sign-in</button>}{!derivSession&&<button onClick={()=>setView('paper')}>Open paper simulation</button>}</footer>
 </main>;
}
