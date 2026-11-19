'use client'
import * as React from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { ScrollArea } from '@/components/ui/scroll-area'
import { LineChart } from '@/components/charts/candlestick-chart'
import { useToast } from '@/hooks/use-toast'
import { CheckCircle2, FlaskConical, AlertCircle } from 'lucide-react'

export function StrategyCenter() {
  const qc = useQueryClient()
  const { toast } = useToast()
  const { data, isLoading } = useQuery({
    queryKey: ['strategies'],
    queryFn: async () => (await fetch('/api/strategies')).json(),
  })
  const [selected, setSelected] = React.useState<string | null>(null)
  const [instrument, setInstrument] = React.useState('EUR/USD')
  const [timeframe, setTimeframe] = React.useState('M15')
  const [days, setDays] = React.useState('60')
  const [fast, setFast] = React.useState('10')
  const [slow, setSlow] = React.useState('30')
  const [slPips, setSlPips] = React.useState('20')
  const [tpPips, setTpPips] = React.useState('40')
  const [size, setSize] = React.useState('1')
  const [result, setResult] = React.useState<null | Record<string, unknown>>(null)
  const [running, setRunning] = React.useState(false)

  React.useEffect(() => {
    if (!selected && data?.strategies?.length) setSelected(data.strategies[0].id)
  }, [data, selected])

  const strategies = data?.strategies ?? []
  const current = strategies.find((s: { id: string }) => s.id === selected)

  const runBacktest = async () => {
    if (!selected) return
    setRunning(true)
    setResult(null)
    try {
      const r = await fetch(`/api/strategies/${selected}/backtest`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          instrument, timeframe, days: parseInt(days, 10),
          params: { fastPeriod: parseInt(fast, 10), slowPeriod: parseInt(slow, 10), stopLossPips: parseInt(slPips, 10), takeProfitPips: parseInt(tpPips, 10), size: parseFloat(size) },
        }),
      })
      const d = await r.json()
      if (!r.ok) throw new Error(d.error || 'Backtest failed')
      setResult(d.result)
      toast({ title: 'Backtest complete', description: `${d.result.trades} trades · net ${d.result.netReturn}` })
    } catch (e) {
      toast({ title: 'Backtest error', description: (e as Error).message, variant: 'destructive' })
    } finally {
      setRunning(false)
    }
  }

  const approve = async () => {
    if (!selected) return
    const r = await fetch(`/api/strategies/${selected}/approve`, { method: 'POST', credentials: 'include' })
    if (!r.ok) return toast({ title: 'Error', description: 'Approve failed', variant: 'destructive' })
    toast({ title: 'Strategy approved' })
    qc.invalidateQueries({ queryKey: ['strategies'] })
  }

  if (isLoading) return <div className="text-sm text-muted-foreground">Loading strategies…</div>

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Card className="lg:col-span-1">
          <CardHeader><CardTitle className="text-sm">Strategy Library</CardTitle><CardDescription>Versioned, approval-gated</CardDescription></CardHeader>
          <CardContent>
            <ScrollArea className="h-96">
              <div className="space-y-2">
                {strategies.map((s: { id: string; name: string; version: number; status: string; description: string }) => (
                  <button
                    key={s.id}
                    onClick={() => setSelected(s.id)}
                    className={`w-full text-left rounded-md border p-3 text-sm transition-colors ${selected === s.id ? 'border-primary bg-primary/5' : 'hover:bg-muted/50'}`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-medium">{s.name}</span>
                      <Badge variant={s.status === 'APPROVED' ? 'default' : s.status === 'VALIDATED' ? 'secondary' : 'outline'}>{s.status}</Badge>
                    </div>
                    <div className="text-xs text-muted-foreground mt-1">v{s.version}</div>
                    <div className="text-xs text-muted-foreground mt-1 line-clamp-2">{s.description}</div>
                  </button>
                ))}
              </div>
            </ScrollArea>
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="text-sm">{current?.name ?? 'Select a strategy'}</CardTitle>
              {current && <Button size="sm" variant="outline" onClick={approve}><CheckCircle2 className="h-4 w-4 mr-1" /> Approve</Button>}
            </div>
            <CardDescription>{current?.description}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {current && (
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3 text-xs">
                <div><div className="text-muted-foreground">Instruments</div><div className="font-medium mt-0.5">{current.instruments}</div></div>
                <div><div className="text-muted-foreground">Timeframes</div><div className="font-medium mt-0.5">{current.timeframes}</div></div>
                <div><div className="text-muted-foreground">Max Drawdown</div><div className="font-medium mt-0.5">{current.maxDrawdownPct}%</div></div>
              </div>
            )}
            <div className="rounded-md border p-3">
              <div className="flex items-center gap-2 text-sm font-medium mb-3"><FlaskConical className="h-4 w-4" /> Backtest Configuration</div>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                <div><Label className="text-xs">Instrument</Label>
                  <Select value={instrument} onValueChange={setInstrument}>
                    <SelectTrigger className="h-8 text-xs"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {['EUR/USD', 'GBP/USD', 'USD/JPY', 'AUD/USD', 'R_100', 'R_75'].map(s => <SelectItem key={s} value={s}>{s}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
                <div><Label className="text-xs">Timeframe</Label>
                  <Select value={timeframe} onValueChange={setTimeframe}>
                    <SelectTrigger className="h-8 text-xs"><SelectValue /></SelectTrigger>
                    <SelectContent>{['M5', 'M15', 'H1', 'H4', 'D1'].map(s => <SelectItem key={s} value={s}>{s}</SelectItem>)}</SelectContent>
                  </Select>
                </div>
                <div><Label className="text-xs">Days</Label><Input value={days} onChange={(e) => setDays(e.target.value)} className="h-8 text-xs" inputMode="numeric" /></div>
                <div><Label className="text-xs">Fast MA</Label><Input value={fast} onChange={(e) => setFast(e.target.value)} className="h-8 text-xs" inputMode="numeric" /></div>
                <div><Label className="text-xs">Slow MA</Label><Input value={slow} onChange={(e) => setSlow(e.target.value)} className="h-8 text-xs" inputMode="numeric" /></div>
                <div><Label className="text-xs">Size</Label><Input value={size} onChange={(e) => setSize(e.target.value)} className="h-8 text-xs" inputMode="decimal" /></div>
                <div><Label className="text-xs">SL (pips)</Label><Input value={slPips} onChange={(e) => setSlPips(e.target.value)} className="h-8 text-xs" inputMode="numeric" /></div>
                <div><Label className="text-xs">TP (pips)</Label><Input value={tpPips} onChange={(e) => setTpPips(e.target.value)} className="h-8 text-xs" inputMode="numeric" /></div>
                <div className="flex items-end"><Button className="h-8 w-full" disabled={running} onClick={runBacktest}>{running ? 'Running…' : 'Run Backtest'}</Button></div>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {result && (
        <Card>
          <CardHeader><CardTitle className="text-sm">Backtest Results</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
              <Metric label="Net Return" value={`$${result.netReturn}`} sub={`${result.netReturnPct}%`} positive={Number(result.netReturn) >= 0} />
              <Metric label="Max Drawdown" value={`$${result.maxDrawdown}`} sub={`${result.maxDrawdownPct}%`} />
              <Metric label="Sharpe" value={String(result.sharpe)} />
              <Metric label="Sortino" value={String(result.sortino)} />
              <Metric label="Calmar" value={String(result.calmar)} />
              <Metric label="Win Rate" value={`${result.winRate}%`} />
              <Metric label="Profit Factor" value={String(result.profitFactor)} />
              <Metric label="Expectancy" value={`$${result.expectancy}`} />
              <Metric label="Trades" value={String(result.trades)} />
              <Metric label="Avg Gain" value={`$${result.avgGain}`} />
              <Metric label="Avg Loss" value={`$${result.avgLoss}`} />
              <Metric label="Tx Costs" value={`$${result.transactionCosts}`} />
            </div>
            {(result.warnings as string[])?.length > 0 && (
              <div className="rounded-md border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-700 dark:text-amber-300 space-y-1">
                {(result.warnings as string[]).map((w, i) => <div key={i} className="flex gap-2"><AlertCircle className="h-3.5 w-3.5 mt-0.5 shrink-0" /><span>{w}</span></div>)}
              </div>
            )}
            <div>
              <div className="text-xs text-muted-foreground mb-1">Equity Curve</div>
              <LineChart points={(result.equityCurve as { ts: string; equity: string }[]).map(p => ({ ts: p.ts, value: parseFloat(p.equity) }))} height={220} color="#16a34a" />
            </div>
          </CardContent>
        </Card>
      )}

      {current?.backtests?.length > 0 && (
        <Card>
          <CardHeader><CardTitle className="text-sm">Prior Backtests</CardTitle></CardHeader>
          <CardContent>
            <ScrollArea className="h-48">
              <div className="space-y-1">
                {current.backtests.map((b: { id: string; instrument: string; timeframe: string; fromDate: string; createdAt: string; resultJson: string }) => {
                  const r = JSON.parse(b.resultJson)
                  return (
                    <div key={b.id} className="flex items-center justify-between rounded-md border px-2.5 py-1.5 text-xs">
                      <div className="flex items-center gap-2">
                        <span className="font-medium">{b.instrument}</span>
                        <span className="text-muted-foreground">{b.timeframe}</span>
                        <span className="text-muted-foreground">{new Date(b.fromDate).toLocaleDateString()}</span>
                      </div>
                      <div className="flex items-center gap-3">
                        <span className="text-muted-foreground">{r.trades} trades</span>
                        <span className={Number(r.netReturn) >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-destructive'}>${r.netReturn}</span>
                        <span className="text-muted-foreground">{new Date(b.createdAt).toLocaleDateString()}</span>
                      </div>
                    </div>
                  )
                })}
              </div>
            </ScrollArea>
          </CardContent>
        </Card>
      )}
    </div>
  )
}

function Metric({ label, value, sub, positive }: { label: string; value: string; sub?: string; positive?: boolean }) {
  return (
    <div className="rounded-md border p-2.5">
      <div className="text-[10px] text-muted-foreground uppercase tracking-wide">{label}</div>
      <div className={`mt-0.5 text-sm font-semibold tabular-nums ${positive === undefined ? '' : positive ? 'text-emerald-600 dark:text-emerald-400' : 'text-destructive'}`}>{value}</div>
      {sub && <div className="text-[10px] text-muted-foreground">{sub}</div>}
    </div>
  )
}
