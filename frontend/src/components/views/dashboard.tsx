'use client'
import * as React from 'react'
import { useQuery } from '@tanstack/react-query'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Progress } from '@/components/ui/progress'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Activity, AlertTriangle, TrendingUp, TrendingDown, Wallet, ShieldAlert, Zap, Plug } from 'lucide-react'
import { LineChart } from '@/components/charts/candlestick-chart'

export function Dashboard({ accountId }: { accountId: string }) {
  const { data, isLoading, refetch } = useQuery({
    queryKey: ['portfolio-summary', accountId],
    queryFn: async () => {
      const r = await fetch(`/api/portfolio/summary?accountId=${accountId}`)
      if (!r.ok) throw new Error('Failed to load')
      return r.json()
    },
    refetchInterval: 5000,
  })

  const { data: emergency } = useQuery({
    queryKey: ['emergency', accountId],
    queryFn: async () => {
      const r = await fetch(`/api/emergency-stop?accountId=${accountId}`)
      return r.json()
    },
  })

  React.useEffect(() => {
    const t = setInterval(() => refetch(), 10000)
    return () => clearInterval(t)
  }, [refetch])

  if (isLoading || !data) {
    return <div className="text-sm text-muted-foreground">Loading dashboard…</div>
  }

  const equity = parseFloat(data.equity ?? '0')
  const balance = parseFloat(data.balance ?? '0')
  const realized = parseFloat(data.realizedPnl ?? '0')
  const unrealized = parseFloat(data.unrealizedPnl ?? '0')
  const fees = parseFloat(data.fees ?? '0')
  const es = data.emergencyStop
  const risk = data.risk
  const equityCurve = (data.closedPositions ?? []).map((p: { closedAt: string; realizedPnl: string }, i: number) => ({
    ts: p.closedAt, value: 10000 + (data.closedPositions ?? []).slice(0, i + 1).reduce((s: number, q: { realizedPnl: string }) => s + parseFloat(q.realizedPnl || '0'), 0)
  })).reverse()

  return (
    <div className="space-y-6">
      {/* KPI cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiCard label="Equity" value={`$${equity.toFixed(2)}`} icon={Wallet} accent={equity >= 10000 ? 'up' : 'down'} />
        <KpiCard label="Cash Balance" value={`$${balance.toFixed(2)}`} icon={Activity} />
        <KpiCard label="Unrealized P&L" value={`${unrealized >= 0 ? '+' : ''}$${unrealized.toFixed(2)}`} icon={unrealized >= 0 ? TrendingUp : TrendingDown} accent={unrealized >= 0 ? 'up' : 'down'} />
        <KpiCard label="Realized P&L" value={`${realized >= 0 ? '+' : ''}$${realized.toFixed(2)}`} icon={realized >= 0 ? TrendingUp : TrendingDown} accent={realized >= 0 ? 'up' : 'down'} />
      </div>

      {/* Account + risk row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Card className="lg:col-span-2">
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between">
              <CardTitle className="text-base">Account Summary</CardTitle>
              <Badge variant="secondary">PAPER · synthetic feed</Badge>
            </div>
            <CardDescription>Mode: {data.account.mode} · Broker: {data.account.broker} · Currency: {data.account.currency}</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
              <Stat label="Open Positions" value={data.openPositions?.length ?? 0} />
              <Stat label="Fees Paid" value={`$${fees.toFixed(2)}`} />
              <Stat label="Recent Orders" value={data.recentOrders?.length ?? 0} />
              <Stat label="LIVE Authorized" value={data.account.liveAuthorized ? 'Yes' : 'No'} highlight={!data.account.liveAuthorized ? 'warn' : undefined} />
            </div>
            <div className="mt-4">
              <div className="text-xs text-muted-foreground mb-1">Equity curve (cumulative realized P&L)</div>
              <LineChart points={equityCurve.length ? equityCurve : [{ ts: 'now', value: 10000 }]} height={160} color="#0ea5e9" />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between">
              <CardTitle className="text-base">Risk & Emergency</CardTitle>
              <ShieldAlert className="h-4 w-4 text-muted-foreground" />
            </div>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground">Emergency Stop</span>
              <Badge variant={es?.active ? 'destructive' : 'outline'}>{es?.active ? 'ACTIVE' : 'INACTIVE'}</Badge>
            </div>
            <div>
              <div className="flex justify-between text-xs mb-1"><span className="text-muted-foreground">Exposure</span><span>{risk?.exposureUtilizationPct ?? 0}%</span></div>
              <Progress value={risk?.exposureUtilizationPct ?? 0} />
            </div>
            <div>
              <div className="flex justify-between text-xs mb-1"><span className="text-muted-foreground">Positions</span><span>{risk?.openPositions ?? 0}/{risk?.maxSimultaneousPositions ?? 0}</span></div>
              <Progress value={risk?.positionsUtilizationPct ?? 0} />
            </div>
            <div className="flex justify-between"><span className="text-muted-foreground">Daily loss limit</span><span>${risk?.dailyLossLimit ?? 0}</span></div>
            <div className="flex justify-between"><span className="text-muted-foreground">Net realized</span><span className={Number(risk?.netRealized ?? 0) < 0 ? 'text-destructive' : ''}>${risk?.netRealized ?? 0}</span></div>
          </CardContent>
        </Card>
      </div>

      {/* Recent activity + positions */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card>
          <CardHeader><CardTitle className="text-base">Open Positions</CardTitle></CardHeader>
          <CardContent>
            {(data.openPositions ?? []).length === 0 ? (
              <Empty text="No open positions." />
            ) : (
              <ScrollArea className="h-64">
                <div className="space-y-2">
                  {data.openPositions.map((p: { id: string; side: string; size: string; entryPrice: string; currentPrice: string; unrealizedPnl: string; instrument: { symbol: string } }) => {
                    const pnl = parseFloat(p.unrealizedPnl)
                    return (
                      <div key={p.id} className="flex items-center justify-between rounded-md border p-2 text-xs">
                        <div className="flex items-center gap-2">
                          <Badge variant={p.side === 'BUY' ? 'default' : 'secondary'}>{p.side}</Badge>
                          <span className="font-medium">{p.instrument.symbol}</span>
                          <span className="text-muted-foreground">{p.size} @ {p.entryPrice}</span>
                        </div>
                        <span className={pnl >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-destructive'}>{pnl >= 0 ? '+' : ''}{pnl.toFixed(2)}</span>
                      </div>
                    )
                  })}
                </div>
              </ScrollArea>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle className="text-base">Recent Orders</CardTitle></CardHeader>
          <CardContent>
            {(data.recentOrders ?? []).length === 0 ? (
              <Empty text="No recent orders." />
            ) : (
              <ScrollArea className="h-64">
                <div className="space-y-2">
                  {data.recentOrders.map((o: { id: string; side: string; type: string; status: string; size: string; avgFillPrice: string | null; createdAt: string; instrument: { symbol: string } }) => (
                    <div key={o.id} className="flex items-center justify-between rounded-md border p-2 text-xs">
                      <div className="flex items-center gap-2">
                        <Badge variant={o.side === 'BUY' ? 'default' : 'secondary'}>{o.side}</Badge>
                        <span className="font-medium">{o.instrument.symbol}</span>
                        <span className="text-muted-foreground">{o.size} {o.type}</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <OrderStatusBadge status={o.status} />
                        <span className="text-muted-foreground">{new Date(o.createdAt).toLocaleTimeString()}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </ScrollArea>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Broker + system status */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card>
          <CardHeader><CardTitle className="text-base flex items-center gap-2"><Plug className="h-4 w-4" /> Broker Connection</CardTitle></CardHeader>
          <CardContent className="text-sm space-y-2">
            <div className="flex justify-between"><span className="text-muted-foreground">Broker</span><span>{data.account.broker}</span></div>
            <div className="flex justify-between"><span className="text-muted-foreground">Mode</span><Badge variant="secondary">{data.account.mode}</Badge></div>
            <div className="flex justify-between"><span className="text-muted-foreground">LIVE Authorized</span><Badge variant={data.account.liveAuthorized ? 'destructive' : 'outline'}>{data.account.liveAuthorized ? 'AUTHORIZED' : 'NOT AUTHORIZED'}</Badge></div>
            <div className="rounded-md bg-muted/50 p-2 text-xs text-muted-foreground mt-2">
              Real broker connections (Deriv/OANDA) are available via Broker Connections. LIVE trading remains disabled until all gates are satisfied.
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle className="text-base flex items-center gap-2"><Zap className="h-4 w-4" /> Strategy Status</CardTitle></CardHeader>
          <CardContent className="text-sm space-y-2">
            <div className="flex justify-between"><span className="text-muted-foreground">Active strategy</span><span>MA Crossover (Fast/Slow)</span></div>
            <div className="flex justify-between"><span className="text-muted-foreground">Approval</span><Badge variant="secondary">VALIDATED</Badge></div>
            <div className="flex justify-between"><span className="text-muted-foreground">Timeframe</span><span>M15</span></div>
            <div className="rounded-md bg-muted/50 p-2 text-xs text-muted-foreground mt-2">
              Backtest and approve strategies in the Strategy Center before any deployment consideration.
            </div>
          </CardContent>
        </Card>
      </div>

      {es?.active && (
        <Card className="border-destructive/40">
          <CardContent className="pt-6 flex items-center gap-3">
            <AlertTriangle className="h-5 w-5 text-destructive" />
            <div className="text-sm">
              <div className="font-medium text-destructive">Emergency stop is ACTIVE</div>
              <div className="text-muted-foreground">{es.reason || 'Manual activation'} · New entries blocked.</div>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}

function KpiCard({ label, value, icon: Icon, accent }: { label: string; value: string; icon: React.ElementType; accent?: 'up' | 'down' }) {
  const color = accent === 'up' ? 'text-emerald-600 dark:text-emerald-400' : accent === 'down' ? 'text-destructive' : 'text-foreground'
  return (
    <Card>
      <CardContent className="pt-5">
        <div className="flex items-center justify-between">
          <span className="text-xs text-muted-foreground">{label}</span>
          <Icon className={`h-4 w-4 ${color}`} />
        </div>
        <div className={`mt-2 text-xl font-semibold tabular-nums ${color}`}>{value}</div>
      </CardContent>
    </Card>
  )
}

function Stat({ label, value, highlight }: { label: string; value: React.ReactNode; highlight?: 'warn' }) {
  return (
    <div>
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className={`mt-0.5 font-medium ${highlight === 'warn' ? 'text-amber-600 dark:text-amber-400' : ''}`}>{value}</div>
    </div>
  )
}

function OrderStatusBadge({ status }: { status: string }) {
  const variant: 'default' | 'secondary' | 'destructive' | 'outline' =
    status === 'FILLED' ? 'default' :
    status === 'REJECTED' || status === 'CANCELLED' ? 'destructive' :
    status === 'PARTIALLY_FILLED' ? 'secondary' : 'outline'
  return <Badge variant={variant}>{status}</Badge>
}

function Empty({ text }: { text: string }) {
  return <div className="text-sm text-muted-foreground py-8 text-center">{text}</div>
}
