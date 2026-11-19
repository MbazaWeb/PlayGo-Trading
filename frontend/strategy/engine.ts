import type { Candle,StrategyConfig,StrategyResult,Signal } from './types';
import { sma,ema,rsi,stdev,atr,crossesUp,crossesDown } from './indicators';
import {validateConfig} from './config';
export const SUPPORTED_STRATEGY_IDS = [
 'moving-average-crossover','ema-crossover','triple-moving-average','macd-crossover',
 'moving-average-pullback','rsi-momentum','rate-of-change','momentum-breakout',
 'rsi-oversold-overbought','bollinger-bands-reversion','z-score-reversion',
 'moving-average-reversion','donchian-channel-breakout','support-resistance-breakout',
 'price-channel-breakout','previous-high-low-breakout','consolidation-breakout',
 'atr-breakout','engulfing-candlestick','pin-bar-reversal','inside-bar-breakout',
 'higher-high-higher-low','trend-momentum-hybrid','ensemble-voting',
] as const;
export type SupportedStrategyId = typeof SUPPORTED_STRATEGY_IDS[number];
export const isSupportedStrategy = (id:string):id is SupportedStrategyId =>
 (SUPPORTED_STRATEGY_IDS as readonly string[]).includes(id);
const done=(signal:Signal,reason:string,c:Candle[]):StrategyResult=>({signal,reason,barTime:c.at(-1)?.ts??null,ready:true});
const hold=(reason:string,c:Candle[]):StrategyResult=>({signal:'HOLD',reason,barTime:c.at(-1)?.ts??null,ready:false});
// Closed candles only. No execution, broker requests or orders are generated here.
export function evaluateStrategy(id:string,c:Candle[],p:StrategyConfig):StrategyResult {
 const errors=validateConfig(p);if(errors.length)return hold(errors.join('; '),c);
 const strategyPeriod=id==='triple-moving-average'?p.slowPeriod*2:id==='macd-crossover'?34:0;
 if(c.length<Math.max(p.slowPeriod,p.bandPeriod,p.breakoutPeriod,p.rsiPeriod,p.atrPeriod,strategyPeriod)+5)return hold('Insufficient closed candles',c);
 if(c.some(x=>![x.open,x.high,x.low,x.close].every(Number.isFinite)||x.high<x.low||x.close<=0))return hold('Invalid OHLC data',c);
 for(let j=1;j<c.length;j++)if(c[j].ts<=c[j-1].ts)return hold('Candles must be sorted and unique',c);
 const close=c.map(x=>x.close),i=close.length-1,fast=ema(close,p.fastPeriod),slow=ema(close,p.slowPeriod),ma=sma(close,p.slowPeriod),rv=rsi(close,p.rsiPeriod),av=atr(c,p.atrPeriod),std=stdev(close,p.bandPeriod),mid=sma(close,p.bandPeriod);
 const trend=fast[i]>slow[i]?'BUY':'SELL';
 const cross=(a:number[],b:number[])=>crossesUp(a,b,i)?'BUY':crossesDown(a,b,i)?'SELL':'HOLD';
 const threshold=(v:number,lo:number,hi:number):Signal=>v<lo?'BUY':v>hi?'SELL':'HOLD';
 const breakout=()=>{const past=c.slice(i-p.breakoutPeriod,i);const hi=Math.max(...past.map(x=>x.high)),lo=Math.min(...past.map(x=>x.low));return close[i]>hi?'BUY':close[i]<lo?'SELL':'HOLD';};
 const band=()=>close[i]<mid[i]-p.bandStdDev*std[i]?'BUY':close[i]>mid[i]+p.bandStdDev*std[i]?'SELL':'HOLD';
 let signal:Signal='HOLD',reason='No qualifying signal';
 switch(id){
 case 'moving-average-crossover': signal=cross(sma(close,p.fastPeriod),ma);break;
 case 'ema-crossover':signal=cross(fast,slow);break;
 case 'triple-moving-average':signal=fast[i]>slow[i]&&slow[i]>sma(close,p.slowPeriod*2)[i]?'BUY':fast[i]<slow[i]&&slow[i]<sma(close,p.slowPeriod*2)[i]?'SELL':'HOLD';break;
 case 'macd-crossover': {const e12=ema(close,12),e26=ema(close,26);const macd=e12.map((v,j)=>v-e26[j]);const valid=macd.slice(25);const line=[...Array(25).fill(NaN),...ema(valid,9)];signal=cross(macd,line);break;}
 case 'moving-average-pullback':signal=close[i]>slow[i]&&c[i].low<=slow[i]?'BUY':close[i]<slow[i]&&c[i].high>=slow[i]?'SELL':'HOLD';break;
 case 'rsi-momentum':signal=rv[i]>55?'BUY':rv[i]<45?'SELL':'HOLD';break;
 case 'rate-of-change':signal=close[i]>close[i-p.fastPeriod]*1.01?'BUY':close[i]<close[i-p.fastPeriod]*0.99?'SELL':'HOLD';break;
 case 'momentum-breakout':signal=breakout();if(signal!=='HOLD'&&((signal==='BUY'&&rv[i]<55)||(signal==='SELL'&&rv[i]>45)))signal='HOLD';break;
 case 'rsi-oversold-overbought':signal=threshold(rv[i],p.rsiOversold,p.rsiOverbought);break;
 case 'bollinger-bands-reversion':case 'z-score-reversion':signal=band();break;
 case 'moving-average-reversion':signal=close[i]<ma[i]-2*av[i]?'BUY':close[i]>ma[i]+2*av[i]?'SELL':'HOLD';break;
 case 'donchian-channel-breakout':case 'support-resistance-breakout':case 'price-channel-breakout':case 'previous-high-low-breakout':case 'consolidation-breakout':signal=breakout();break;
 case 'atr-breakout':signal=close[i]>close[i-1]+1.5*av[i]?'BUY':close[i]<close[i-1]-1.5*av[i]?'SELL':'HOLD';break;
 case 'engulfing-candlestick':{const a=c[i-1],b=c[i];signal=a.close<a.open&&b.close>b.open&&b.open<=a.close&&b.close>=a.open?'BUY':a.close>a.open&&b.close<b.open&&b.open>=a.close&&b.close<=a.open?'SELL':'HOLD';break;}
 case 'pin-bar-reversal':{const b=c[i],range=b.high-b.low,body=Math.abs(b.close-b.open);signal=range>0&&body/range<0.35&&Math.min(b.open,b.close)-b.low>range*0.6?'BUY':range>0&&body/range<0.35&&b.high-Math.max(b.open,b.close)>range*0.6?'SELL':'HOLD';break;}
 case 'inside-bar-breakout':signal=c[i-1].high<c[i-2].high&&c[i-1].low>c[i-2].low?(close[i]>c[i-2].high?'BUY':close[i]<c[i-2].low?'SELL':'HOLD'):'HOLD';break;
 case 'higher-high-higher-low':signal=c[i].high>c[i-1].high&&c[i].low>c[i-1].low?'BUY':c[i].high<c[i-1].high&&c[i].low<c[i-1].low?'SELL':'HOLD';break;
 case 'trend-momentum-hybrid':signal=trend==='BUY'&&rv[i]>55?'BUY':trend==='SELL'&&rv[i]<45?'SELL':'HOLD';break;
 case 'ensemble-voting':{const votes=[trend,threshold(rv[i],40,60),breakout()];signal=votes.filter(x=>x==='BUY').length>=2?'BUY':votes.filter(x=>x==='SELL').length>=2?'SELL':'HOLD';break;}
 default:return hold('Research-only strategy: requires validated specialist model or additional market/session data; no fabricated signal',c);
 }
 return done(signal,signal==='HOLD'?'Conditions not met':`Rule-based ${id} signal on latest CLOSED candle; not an order`,c);
}
