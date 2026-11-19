 'use client';
import React,{useState} from 'react';
import {strategies} from './registry';
import {DEFAULT_CONFIG,validateConfig} from './config';
import type {Candle,StrategyConfig} from './types';
export default function StrategyConfigurator({candles=[]}:{candles?:Candle[]}){
 const [id,setId]=useState(strategies[0].id);const [config,setConfig]=useState<StrategyConfig>(DEFAULT_CONFIG);
 const [output,setOutput]=useState('');const selected=strategies.find(s=>s.id===id)!;
 const numeric:(keyof StrategyConfig)[]=['fastPeriod','slowPeriod','rsiPeriod','rsiOversold','rsiOverbought','bandPeriod','bandStdDev','atrPeriod','atrMultiplier','breakoutPeriod','riskPct','stopLossPct','rewardRisk'];
 const update=(key:keyof StrategyConfig,value:unknown)=>setConfig(prev=>({...prev,[key]:value}));
 const errors=validateConfig(config);
 return <section style={{maxWidth:760,padding:20,border:'1px solid #777',borderRadius:12,display:'grid',gap:12}}><h2>PlayGo Strategy Configuration — PAPER ONLY</h2>
 <label>Strategy <select value={id} onChange={e=>{setId(e.target.value);setOutput('');}}>{strategies.map(s=><option key={s.id} value={s.id}>{s.category} — {s.name}</option>)}</select></label>
 <label>Timeframe <select value={config.timeframe} onChange={e=>update('timeframe',e.target.value)}>{['1m','5m','15m','1h','4h','1d'].map(v=><option key={v}>{v}</option>)}</select></label>
 <label>Stop-loss <select value={config.stopLossMethod} onChange={e=>update('stopLossMethod',e.target.value)}>{['atr','structure','fixed'].map(v=><option key={v}>{v}</option>)}</select></label>
 <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(180px,1fr))',gap:12}}>{numeric.map(key=><label key={key} style={{display:'grid'}}>{key}<input type="number" step="any" value={config[key] as number} onChange={e=>update(key,e.target.value===''?NaN:Number(e.target.value))}/></label>)}</div>
 <p>Execution: PAPER only. Configuration does not submit orders.</p>{errors.length>0&&<p role="alert">{errors.join('; ')}</p>}
 <button disabled={errors.length>0} onClick={()=>setOutput(JSON.stringify({strategyId:id,config},null,2))}>Export configuration JSON</button>
 <button disabled={errors.length>0||candles.length===0} onClick={()=>setOutput(JSON.stringify(selected.evaluate(candles,config),null,2))}>Evaluate closed candles (signal only)</button>
 <pre style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere'}}>{output||'Supply closed candles to evaluate; export works without candles.'}</pre></section>;
}
