"""PlayGo Forex paper-trading starter. Synthetic quotes only; never routes live orders."""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime, timezone
from uuid import uuid4
import random, os

app = FastAPI(title='PlayGo AI Trading', version='0.1.0')
app.add_middleware(CORSMiddleware, allow_origins=os.getenv('CORS_ORIGINS','http://localhost:5173').split(','), allow_methods=['GET','POST'], allow_headers=['*'])
PAIRS={'EURUSD':(1.085,0.0001,0.00012),'GBPUSD':(1.265,0.0001,0.00018),'USDJPY':(151.0,0.01,0.018)}
state={'balance':10000.0,'starting_balance':10000.0,'day_start_balance':10000.0,'positions':[],'trades':[],'logs':[],'paused':True,'quotes':{},'ticks':0}
random.seed(12)
for p,(mid,pip,spread) in PAIRS.items(): state['quotes'][p]={'bid':round(mid-spread/2,5 if pip<0.01 else 3),'ask':round(mid+spread/2,5 if pip<0.01 else 3),'pip':pip,'spread':spread}

def log(agent,message):
    state['logs'].insert(0,{'id':str(uuid4()),'time':datetime.now(timezone.utc).isoformat(),'agent':agent,'message':message})
    state['logs']=state['logs'][:100]

def equity():
    pnl=sum((state['quotes'][p['pair']]['bid']-p['entry'] if p['side']=='BUY' else p['entry']-state['quotes'][p['pair']]['ask'])*p['units'] for p in state['positions'])
    return round(state['balance']+pnl,2)

def snapshot():
    return {'mode':'PAPER','feed':'SYNTHETIC','balance':round(state['balance'],2),'equity':equity(),'paused':state['paused'],'positions':state['positions'],'trades':state['trades'][-30:][::-1],'logs':state['logs'][:30],'quotes':state['quotes'],'agents':['Scanner','Strategy','Risk Checker','Executor','Logger','Supervisor']}

class Order(BaseModel):
    pair:str
    side:str
    stop_pips:float=20
    take_profit_pips:float=40

@app.get('/api/status')
def status():return snapshot()

@app.post('/api/start')
def start():
    state['paused']=False;log('Supervisor','Paper engine enabled; synthetic feed only');return snapshot()

@app.post('/api/stop')
def stop():
    state['paused']=True;log('Supervisor','New entries disabled; existing positions remain monitored');return snapshot()

@app.post('/api/tick')
def tick():
    # Development-only synthetic market feed. Replace with verified broker data before realistic paper testing.
    for pair,(mid,pip,spread) in PAIRS.items():
        q=state['quotes'][pair];center=(q['bid']+q['ask'])/2+random.gauss(0,pip*2)
        q['bid']=round(center-spread/2,5 if pip<0.01 else 3);q['ask']=round(center+spread/2,5 if pip<0.01 else 3)
    state['ticks']+=1
    log('Scanner',f'Scanned {len(PAIRS)} synthetic FX pairs (tick {state["ticks"]})')
    for pos in list(state['positions']):
        price=state['quotes'][pos['pair']]['bid' if pos['side']=='BUY' else 'ask']
        hit=(price<=pos['stop'] or price>=pos['target']) if pos['side']=='BUY' else (price>=pos['stop'] or price<=pos['target'])
        if hit: close_position(pos['id'],'SL/TP')
    if state['balance']<=state['day_start_balance']*.98:
        state['paused']=True;log('Supervisor','Daily loss limit triggered: entries disabled')
    return snapshot()

def close_position(position_id,reason):
    pos=next((p for p in state['positions'] if p['id']==position_id),None)
    if not pos:raise HTTPException(404,'Position not found')
    q=state['quotes'][pos['pair']];exit_price=q['bid' if pos['side']=='BUY' else 'ask']
    pnl=round((exit_price-pos['entry'] if pos['side']=='BUY' else pos['entry']-exit_price)*pos['units'],2)
    state['balance']=round(state['balance']+pnl,2)
    state['positions'].remove(pos);state['trades'].append({**pos,'exit':exit_price,'pnl':pnl,'reason':reason})
    log('Logger',f'Closed {pos["pair"]} {pos["side"]}: P&L ${pnl:.2f} ({reason})')
    return snapshot()

@app.post('/api/orders')
def order(req:Order):
    pair=req.pair.upper();side=req.side.upper()
    if state['paused']:raise HTTPException(403,'Trading paused')
    if pair not in PAIRS or side not in ('BUY','SELL'):raise HTTPException(400,'Unsupported pair or side')
    if not 5<=req.stop_pips<=100 or not 5<=req.take_profit_pips<=300:raise HTTPException(400,'Invalid stop or target distance')
    if len(state['positions'])>=3:raise HTTPException(400,'Maximum open positions reached')
    if any(p['pair']==pair for p in state['positions']):raise HTTPException(400,'Only one position per pair')
    if state['balance']<=state['day_start_balance']*.98:raise HTTPException(400,'Daily loss limit')
    q=state['quotes'][pair];pip=q['pip'];entry=q['ask' if side=='BUY' else 'bid']
    risk_budget=min(equity()*.005,max(0,equity()*.015-sum(p['risk_usd'] for p in state['positions'])))
    # Includes the entry/exit spread in the worst-case stop distance.
    effective_stop=req.stop_pips*pip+q['spread']
    units=int(risk_budget/effective_stop)
    if units<1:raise HTTPException(400,'Insufficient risk budget')
    stop=entry+(-1 if side=='BUY' else 1)*req.stop_pips*pip
    target=entry+(1 if side=='BUY' else -1)*req.take_profit_pips*pip
    # USDJPY P&L is denominated in JPY; this starter uses USD quote pairs only for safe USD P&L.
    if pair=='USDJPY':raise HTTPException(400,'USDJPY disabled until quote-currency conversion is implemented')
    if units*entry>equity():raise HTTPException(400,'Unleveraged notional exceeds equity')
    pos={'id':str(uuid4()),'pair':pair,'side':side,'entry':entry,'stop':round(stop,5),'target':round(target,5),'units':units,'risk_usd':round(units*effective_stop,2),'opened_at':datetime.now(timezone.utc).isoformat()}
    state['positions'].append(pos);log('Risk Checker',f'Approved {pair}: max risk ${pos["risk_usd"]}');log('Executor',f'PAPER {side} {units} {pair} @ {entry}')
    return snapshot()

@app.post('/api/positions/{position_id}/close')
def close(position_id:str):return close_position(position_id,'MANUAL')

@app.get('/api/health')
def health():return {'ok':True,'mode':'PAPER','feed':'SYNTHETIC'}
