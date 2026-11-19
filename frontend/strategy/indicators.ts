import type { Candle } from './types';
export const sma=(a:number[],n:number):number[]=>a.map((_,i)=>i<n-1?NaN:a.slice(i-n+1,i+1).reduce((x,y)=>x+y,0)/n);
export function ema(a:number[],n:number):number[]{let v=NaN;const k=2/(n+1);return a.map((x,i)=>{if(i<n-1)return NaN;if(i===n-1){v=a.slice(0,n).reduce((p,q)=>p+q,0)/n;return v;}v=x*k+v*(1-k);return v;});}
export function stdev(a:number[],n:number){const m=sma(a,n);return a.map((_,i)=>i<n-1?NaN:Math.sqrt(a.slice(i-n+1,i+1).reduce((s,x)=>s+(x-m[i])**2,0)/n));}
export function rsi(a:number[],n:number){return a.map((_,i)=>{if(i<n)return NaN;let gain=0,loss=0;for(let j=i-n+1;j<=i;j++){const d=a[j]-a[j-1];gain+=Math.max(d,0);loss+=Math.max(-d,0);}return loss===0?(gain===0?50:100):100-100/(1+gain/loss);});}
export function atr(c:Candle[],n:number){const tr=c.map((x,i)=>i?Math.max(x.high-x.low,Math.abs(x.high-c[i-1].close),Math.abs(x.low-c[i-1].close)):x.high-x.low);return sma(tr,n);}
export const crossesUp=(a:number[],b:number[],i:number)=>i>0&&Number.isFinite(a[i-1])&&Number.isFinite(b[i-1])&&a[i-1]<=b[i-1]&&a[i]>b[i];
export const crossesDown=(a:number[],b:number[],i:number)=>i>0&&Number.isFinite(a[i-1])&&Number.isFinite(b[i-1])&&a[i-1]>=b[i-1]&&a[i]<b[i];
