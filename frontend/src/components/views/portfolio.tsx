'use client'
import * as React from 'react'
import { useQuery } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { LineChart } from '@/components/charts/candlestick-chart'

export function Portfolio({ accountId }: { accountId: string }) {
  const [tab, setTab] = React.useState<'open' | 'closed'>('open')
  const { data, isLoading } = useQuery({
    queryKey: ['portfolio', accountId],
    queryFn: async () => (await fetch(`/api/portfolio/summary?accountId=${accountId}`)).json(),
    refetchInterval: 5000,
  })

  if (isLoading || !data) return <div className="text-sm text-muted-foreground">Loading portfolio…</div>

  const open = (data.openPositions ?? [])
  const closed = (data.closedPositions ?? [])
  const totalRealized = closed.reduce((s: number, p: { realizedPnl: string }) => s + parseFloat(p.realizedPnl || '0'), 0)
  const equityCurve = [...closed].reverse().map((p: { closedAt: string; realizedPnl: string }, i: number, arr: { realizedPnl: string }[]) => ({
    ts: p.closedAt,
    value: 10000 + arr.slice(0, i + 1).reduce((s: number, q: { realizedPnl: string }) => s + parseFloat(q.realizedPnl || '0'), 0)
  }))

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <Card><CardContent className="pt-5"><div className="text-xs text-muted-foreground">Equity</div><div className="mt-1 text-xl font-semibold tabular-nums">${parseFloat(data.equity).toFixed(2)}</div></CardContent></Card>
        <Card><CardContent className="pt-5"><div className="text-xs text-muted-foreground">Cash</div><div className="mt-1 text-xl font-semibold tabular-nums">${parseFloat(data.balance).toFixed(2)}</div></CardContent></Card>
        <Card><CardContent className="pt-5"><div className="text-xs text-muted-foreground">Unrealized</div><div className={`mt-1 text-xl font-semibold tabular-nums ${parseFloat(data.unrealizedPnl) >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-destructive'}`}>{parseFloat(data.unrealizedPnl) >= 0 ? '+' : ''}${parseFloat(data.unrealizedPnl).toFixed(2)}</div></CardContent></Card>
        <Card><CardContent className="pt-5"><div className="text-xs text-muted-foreground">Realized (total)</div><div className={`mt-1 text-xl font-semibold tabular-nums ${totalRealized >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-destructive'}`}>{totalRealized >= 0 ? '+' : ''}${totalRealized.toFixed(2)}</div></CardContent></Card>
      </div>

      <Card>
        <CardHeader className="pb-2"><CardTitle className="text-sm">Equity History</CardTitle></CardHeader>
        <CardContent><LineChart points={equityCurve.length ? equityCurve : [{ ts: 'now', value: 10000 }]} height={220} color="#0ea5e9" /></CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <CardTitle className="text-sm">Positions</CardTitle>
            <Tabs value={tab} onValueChange={(v) => setTab(v as 'open' | 'closed')}>
              <TabsList className="h-8"><TabsTrigger value="open" className="text-xs">Open ({open.length})</TabsTrigger><TabsTrigger value="closed" className="text-xs">Closed ({closed.length})</TabsTrigger></TabsList>
            </Tabs>
          </div>
        </CardHeader>
        <CardContent>
          <ScrollArea className="h-96">
            <div className="space-y-1">
              {tab === 'open' ? (
                open.length === 0 ? <div className="text-sm text-muted-foreground py-8 text-center">No open positions.</div> :
                open.map((p: { id: string; side: string; size: string; entryPrice: string; currentPrice: string; unrealizedPnl: string; commission: string; swap: string; openedAt: string; instrument: { symbol: string } }) => {
                  const pnl = parseFloat(p.unrealizedPnl)
                  return (
                    <div key={p.id} className="flex items-center justify-between rounded-md border px-2.5 py-2 text-xs">
                      <div className="flex items-center gap-2">
                        <Badge variant={p.side === 'BUY' ? 'default' : 'secondary'}>{p.side}</Badge>
                        <span className="font-medium">{p.instrument.symbol}</span>
                        <span className="text-muted-foreground">{p.size} @ {p.entryPrice}</span>
                        <span className="text-muted-foreground">→ {p.currentPrice}</span>
                      </div>
                      <div className="flex items-center gap-3">
                        <span className="text-muted-foreground">comm ${parseFloat(p.commission).toFixed(2)}</span>
                        <span className={pnl >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-destructive'}>{pnl >= 0 ? '+' : ''}{pnl.toFixed(2)}</span>
                      </div>
                    </div>
                  )
                })
              ) : (
                closed.length === 0 ? <div className="text-sm text-muted-foreground py-8 text-center">No closed positions yet.</div> :
                closed.map((p: { id: string; side: string; size: string; entryPrice: string; realizedPnl: string; commission: string; closedAt: string; instrument: { symbol: string } }) => {
                  const pnl = parseFloat(p.realizedPnl)
                  return (
                    <div key={p.id} className="flex items-center justify-between rounded-md border px-2.5 py-2 text-xs">
                      <div className="flex items-center gap-2">
                        <Badge variant={p.side === 'BUY' ? 'default' : 'secondary'}>{p.side}</Badge>
                        <span className="font-medium">{p.instrument.symbol}</span>
                        <span className="text-muted-foreground">{p.size} @ {p.entryPrice}</span>
                      </div>
                      <div className="flex items-center gap-3">
                        <span className="text-muted-foreground">{p.closedAt ? new Date(p.closedAt).toLocaleString() : ''}</span>
                        <span className={pnl >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-destructive'}>{pnl >= 0 ? '+' : ''}{pnl.toFixed(2)}</span>
                      </div>
                    </div>
                  )
                })
              )}
            </div>
          </ScrollArea>
        </CardContent>
      </Card>
    </div>
  )
}
