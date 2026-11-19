'use client'
import * as React from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { CandlestickChart } from '@/components/charts/candlestick-chart'
import { useToast } from '@/hooks/use-toast'
import { TrendingUp, TrendingDown } from 'lucide-react'

const TIMEFRAMES = ['M1', 'M5', 'M15', 'H1', 'H4', 'D1']

export function TradingTerminal({ accountId }: { accountId: string }) {
  const qc = useQueryClient()
  const { toast } = useToast()
  const [symbol, setSymbol] = React.useState('EUR/USD')
  const [timeframe, setTimeframe] = React.useState('M15')
  const [side, setSide] = React.useState<'BUY' | 'SELL'>('BUY')
  const [size, setSize] = React.useState('1')
  const [sl, setSl] = React.useState('')
  const [tp, setTp] = React.useState('')
  const [submitting, setSubmitting] = React.useState(false)

  const { data: instruments } = useQuery({
    queryKey: ['instruments'],
    queryFn: async () => (await fetch('/api/market/instruments')).json(),
  })

  const { data: quote } = useQuery({
    queryKey: ['quote', symbol],
    queryFn: async () => (await fetch(`/api/market/quote?symbol=${encodeURIComponent(symbol)}`)).json(),
    refetchInterval: 3000,
  })

  const { data: candles, refetch: refetchCandles } = useQuery({
    queryKey: ['candles', symbol, timeframe],
    queryFn: async () => (await fetch(`/api/market/candles?symbol=${encodeURIComponent(symbol)}&timeframe=${timeframe}&bars=120`)).json(),
    refetchInterval: 5000,
  })

  const { data: positions } = useQuery({
    queryKey: ['positions', accountId],
    queryFn: async () => (await fetch(`/api/positions?accountId=${accountId}`)).json(),
    refetchInterval: 5000,
  })

  const { data: orders } = useQuery({
    queryKey: ['orders', accountId],
    queryFn: async () => (await fetch(`/api/orders?accountId=${accountId}`)).json(),
    refetchInterval: 5000,
  })

  const submitOrder = async () => {
    setSubmitting(true)
    try {
      const r = await fetch('/api/orders', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          accountId, symbol, side, type: 'MARKET', size,
          stopLoss: sl || null, takeProfit: tp || null,
        }),
      })
      const data = await r.json()
      if (!r.ok) throw new Error(data.error || 'Order rejected')
      const status = data.order?.status
      if (status === 'FILLED') {
        toast({ title: 'Order filled', description: `${side} ${size} ${symbol} @ ${data.order.avgFillPrice}` })
      } else if (status === 'REJECTED') {
        toast({ title: 'Order rejected', description: data.order?.rejectReason || 'Rejected by risk engine', variant: 'destructive' })
      } else {
        toast({ title: `Order ${status}`, description: `${side} ${size} ${symbol}` })
      }
      setSize('1'); setSl(''); setTp('')
      qc.invalidateQueries({ queryKey: ['positions', accountId] })
      qc.invalidateQueries({ queryKey: ['orders', accountId] })
      refetchCandles()
    } catch (e) {
      toast({ title: 'Error', description: (e as Error).message, variant: 'destructive' })
    } finally {
      setSubmitting(false)
    }
  }

  const closePosition = async (id: string) => {
    const r = await fetch(`/api/positions/${id}/close`, { method: 'POST', credentials: 'include' })
    const data = await r.json()
    if (!r.ok) return toast({ title: 'Error', description: data.error, variant: 'destructive' })
    toast({ title: 'Position closed', description: `Realized P&L $${data.realizedPnl}` })
    qc.invalidateQueries({ queryKey: ['positions', accountId] })
  }

  const q = quote?.quote
  const bid = q ? parseFloat(q.bid) : 0
  const ask = q ? parseFloat(q.ask) : 0
  const spread = q ? parseFloat(q.spread) : 0

  return (
    <div className="space-y-4">
      {/* Top: symbol + quote */}
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
        <Card className="lg:col-span-1">
          <CardHeader className="pb-2"><CardTitle className="text-sm">Instrument</CardTitle></CardHeader>
          <CardContent>
            <Select value={symbol} onValueChange={setSymbol}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                {(instruments?.instruments ?? []).map((i: { symbol: string; kind: string; description: string }) => (
                  <SelectItem key={i.symbol} value={i.symbol}>
                    <span className="font-medium">{i.symbol}</span>
                    <span className="ml-2 text-xs text-muted-foreground">{i.kind}</span>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <div className="mt-3 text-xs text-muted-foreground">
              {(instruments?.instruments ?? []).find((i: { symbol: string }) => i.symbol === symbol)?.description}
            </div>
          </CardContent>
        </Card>

        <Card className="lg:col-span-3">
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between">
              <CardTitle className="text-sm">{symbol} · {timeframe}</CardTitle>
              <Tabs value={timeframe} onValueChange={setTimeframe}>
                <TabsList className="h-7">
                  {TIMEFRAMES.map(tf => <TabsTrigger key={tf} value={tf} className="text-xs px-2 h-6">{tf}</TabsTrigger>)}
                </TabsList>
              </Tabs>
            </div>
          </CardHeader>
          <CardContent>
            {q && (
              <div className="flex flex-wrap items-center gap-4 mb-3 text-sm">
                <div className="flex items-center gap-1.5">
                  <TrendingUp className="h-4 w-4 text-emerald-600 dark:text-emerald-400" />
                  <span className="text-muted-foreground">Bid</span>
                  <span className="font-mono font-medium">{bid.toFixed(q.precision)}</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <TrendingDown className="h-4 w-4 text-destructive" />
                  <span className="text-muted-foreground">Ask</span>
                  <span className="font-mono font-medium">{ask.toFixed(q.precision)}</span>
                </div>
                <div className="text-muted-foreground">Spread <span className="font-mono">{spread.toFixed(q.precision)}</span></div>
                <Badge variant="secondary" className="text-[10px]">synthetic · PAPER</Badge>
              </div>
            )}
            <CandlestickChart candles={candles?.candles ?? []} height={300} />
          </CardContent>
        </Card>
      </div>

      {/* Order ticket + positions */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm">Order Ticket</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            <div>
              <Label className="text-xs">Direction</Label>
              <div className="grid grid-cols-2 gap-2 mt-1">
                <Button type="button" variant={side === 'BUY' ? 'default' : 'outline'} className="bg-emerald-600 hover:bg-emerald-600/90 text-white" onClick={() => setSide('BUY')}>
                  BUY
                </Button>
                <Button type="button" variant={side === 'SELL' ? 'default' : 'outline'} className="bg-destructive hover:bg-destructive/90 text-white" onClick={() => setSide('SELL')}>
                  SELL
                </Button>
              </div>
            </div>
            <div>
              <Label className="text-xs" htmlFor="size">Size (lots)</Label>
              <Input id="size" value={size} onChange={(e) => setSize(e.target.value)} inputMode="decimal" />
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <Label className="text-xs" htmlFor="sl">Stop Loss</Label>
                <Input id="sl" value={sl} onChange={(e) => setSl(e.target.value)} placeholder="optional" inputMode="decimal" />
              </div>
              <div>
                <Label className="text-xs" htmlFor="tp">Take Profit</Label>
                <Input id="tp" value={tp} onChange={(e) => setTp(e.target.value)} placeholder="optional" inputMode="decimal" />
              </div>
            </div>
            {q && (
              <div className="rounded-md bg-muted/50 p-2 text-xs space-y-1">
                <div className="flex justify-between"><span className="text-muted-foreground">Fill price (est.)</span><span className="font-mono">{(side === 'BUY' ? ask : bid).toFixed(q.precision)}</span></div>
                <div className="flex justify-between"><span className="text-muted-foreground">Est. commission</span><span className="font-mono">${(parseFloat(size || '0') * (side === 'BUY' ? ask : bid) * 0.00007).toFixed(2)}</span></div>
                <div className="flex justify-between"><span className="text-muted-foreground">Notional</span><span className="font-mono">${(parseFloat(size || '0') * (side === 'BUY' ? ask : bid)).toFixed(2)}</span></div>
              </div>
            )}
            <Button className="w-full" disabled={submitting} onClick={submitOrder}>
              {submitting ? 'Submitting…' : `Submit ${side} ${symbol}`}
            </Button>
            <div className="text-[10px] text-muted-foreground text-center">
              Orders pass through validation, risk approval, and emergency-stop checks before fill.
            </div>
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader className="pb-2"><CardTitle className="text-sm">Open Positions</CardTitle></CardHeader>
          <CardContent>
            {(positions?.positions ?? []).filter((p: { status: string }) => p.status === 'OPEN').length === 0 ? (
              <div className="text-sm text-muted-foreground py-6 text-center">No open positions.</div>
            ) : (
              <ScrollArea className="h-72">
                <div className="space-y-2">
                  {(positions?.positions ?? []).filter((p: { status: string }) => p.status === 'OPEN').map((p: { id: string; side: string; size: string; entryPrice: string; currentPrice: string; unrealizedPnl: string; instrument: { symbol: string } }) => {
                    const pnl = parseFloat(p.unrealizedPnl)
                    return (
                      <div key={p.id} className="flex items-center justify-between rounded-md border p-2.5 text-xs">
                        <div className="flex items-center gap-2">
                          <Badge variant={p.side === 'BUY' ? 'default' : 'secondary'}>{p.side}</Badge>
                          <span className="font-medium">{p.instrument.symbol}</span>
                          <span className="text-muted-foreground">{p.size} @ {p.entryPrice}</span>
                          <span className="text-muted-foreground">→ {p.currentPrice}</span>
                        </div>
                        <div className="flex items-center gap-2">
                          <span className={pnl >= 0 ? 'text-emerald-600 dark:text-emerald-400 font-medium' : 'text-destructive font-medium'}>{pnl >= 0 ? '+' : ''}{pnl.toFixed(2)}</span>
                          <Button size="sm" variant="outline" onClick={() => closePosition(p.id)}>Close</Button>
                        </div>
                      </div>
                    )
                  })}
                </div>
              </ScrollArea>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Order history */}
      <Card>
        <CardHeader className="pb-2"><CardTitle className="text-sm">Order History</CardTitle></CardHeader>
        <CardContent>
          {(orders?.orders ?? []).length === 0 ? (
            <div className="text-sm text-muted-foreground py-6 text-center">No orders yet.</div>
          ) : (
            <ScrollArea className="h-72">
              <div className="space-y-1">
                {(orders?.orders ?? []).slice(0, 50).map((o: { id: string; side: string; type: string; status: string; size: string; avgFillPrice: string | null; rejectReason: string | null; createdAt: string; instrument: { symbol: string } }) => (
                  <div key={o.id} className="flex items-center justify-between rounded-md border px-2.5 py-1.5 text-xs">
                    <div className="flex items-center gap-2">
                      <Badge variant={o.side === 'BUY' ? 'default' : 'secondary'}>{o.side}</Badge>
                      <span className="font-medium">{o.instrument.symbol}</span>
                      <span className="text-muted-foreground">{o.size} {o.type}</span>
                      {o.avgFillPrice && <span className="text-muted-font">@ {o.avgFillPrice}</span>}
                    </div>
                    <div className="flex items-center gap-2">
                      <Badge variant={o.status === 'FILLED' ? 'default' : o.status === 'REJECTED' || o.status === 'CANCELLED' ? 'destructive' : 'outline'}>{o.status}</Badge>
                      {o.rejectReason && <span className="text-destructive truncate max-w-[200px]">{o.rejectReason}</span>}
                      <span className="text-muted-foreground">{new Date(o.createdAt).toLocaleString()}</span>
                    </div>
                  </div>
                ))}
              </div>
            </ScrollArea>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
