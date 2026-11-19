'use client'
import * as React from 'react'
import { useQuery } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Progress } from '@/components/ui/progress'
import { useToast } from '@/hooks/use-toast'
import { CalendarCheck, RefreshCw } from 'lucide-react'

export function Accounting({ accountId }: { accountId: string }) {
  const [tab, setTab] = React.useState<'journals' | 'ledger' | 'events' | 'integrity' | 'phaseA'>('journals')
  const { toast } = useToast()
  const { data: recon, refetch: refetchRecon } = useQuery({
    queryKey: ['reconciliation', accountId],
    queryFn: async () => (await fetch(`/api/reconciliation/list?accountId=${accountId}`)).json(),
  })
  const [running, setRunning] = React.useState(false)
  const runRecon = async () => {
    setRunning(true)
    try {
      const r = await fetch(`/api/reconciliation/run?accountId=${accountId}`, { method: 'POST', credentials: 'include' })
      const d = await r.json()
      if (!r.ok) throw new Error(d.error || 'Reconciliation failed')
      toast({ title: 'Reconciliation recorded', description: `${d.observation.status} · ${d.progress.consecutiveCleanDays}/30 consecutive clean days` })
      refetchRecon()
    } catch (e) {
      toast({ title: 'Error', description: (e as Error).message, variant: 'destructive' })
    } finally {
      setRunning(false)
    }
  }
  const { data: journals } = useQuery({
    queryKey: ['journals', accountId],
    queryFn: async () => (await fetch(`/api/accounting/journals?accountId=${accountId}`)).json(),
  })
  const { data: ledger } = useQuery({
    queryKey: ['ledger', accountId],
    queryFn: async () => (await fetch(`/api/accounting/ledger?accountId=${accountId}`)).json(),
  })
  const { data: tb } = useQuery({
    queryKey: ['trial-balance', accountId],
    queryFn: async () => (await fetch(`/api/accounting/trial-balance?accountId=${accountId}`)).json(),
    refetchInterval: 5000,
  })
  const { data: integrity, refetch: refetchIntegrity } = useQuery({
    queryKey: ['integrity', accountId],
    queryFn: async () => (await fetch(`/api/accounting/verify-integrity?accountId=${accountId}`)).json(),
  })

  return (
    <div className="space-y-4">
      {/* Trial balance summary */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <Card><CardContent className="pt-5"><div className="text-xs text-muted-foreground">Cash Balance</div><div className="mt-1 text-xl font-semibold tabular-nums">${parseFloat(tb?.cash ?? '0').toFixed(2)}</div></CardContent></Card>
        <Card><CardContent className="pt-5"><div className="text-xs text-muted-foreground">Realized P&L</div><div className={`mt-1 text-xl font-semibold tabular-nums ${parseFloat(tb?.realizedPnl ?? '0') >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-destructive'}`}>${parseFloat(tb?.realizedPnl ?? '0').toFixed(2)}</div></CardContent></Card>
        <Card><CardContent className="pt-5"><div className="text-xs text-muted-foreground">Fees</div><div className="mt-1 text-xl font-semibold tabular-nums">${parseFloat(tb?.fees ?? '0').toFixed(2)}</div></CardContent></Card>
        <Card><CardContent className="pt-5"><div className="text-xs text-muted-foreground">Equity</div><div className="mt-1 text-xl font-semibold tabular-nums">${parseFloat(tb?.equity ?? '0').toFixed(2)}</div></CardContent></Card>
      </div>

      <Card>
        <CardContent className="pt-5">
          <div className="flex items-center justify-between flex-wrap gap-2">
            <div className="text-sm">
              <span className="font-medium">Trial Balance: </span>
              <span className="text-muted-foreground">Debit </span><span className="font-mono">${parseFloat(tb?.trialBalance?.debit ?? '0').toFixed(2)}</span>
              <span className="text-muted-foreground"> · Credit </span><span className="font-mono">${parseFloat(tb?.trialBalance?.credit ?? '0').toFixed(2)}</span>
            </div>
            <Badge variant={tb?.trialBalance?.balanced ? 'default' : 'destructive'}>{tb?.trialBalance?.balanced ? 'BALANCED' : 'OUT OF BALANCE'}</Badge>
          </div>
        </CardContent>
      </Card>

      <Tabs value={tab} onValueChange={(v) => setTab(v as 'journals' | 'ledger' | 'events' | 'integrity' | 'phaseA')}>
        <TabsList>
          <TabsTrigger value="journals">Journals</TabsTrigger>
          <TabsTrigger value="ledger">Ledger Entries</TabsTrigger>
          <TabsTrigger value="events">Trade Events</TabsTrigger>
          <TabsTrigger value="integrity">Integrity</TabsTrigger>
          <TabsTrigger value="phaseA">Phase A Observation</TabsTrigger>
        </TabsList>
      </Tabs>

      {tab === 'journals' && (
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm">Accounting Journals <Badge variant="secondary" className="ml-2">append-only</Badge></CardTitle></CardHeader>
          <CardContent>
            <ScrollArea className="h-96">
              <div className="space-y-1">
                {(journals?.journals ?? []).map((j: { id: string; ref: string; type: string; description: string; integrityHash: string | null; createdAt: string; entries: { accountType: string; debit: string; credit: string }[] }) => (
                  <div key={j.id} className="rounded-md border p-2.5 text-xs">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <Badge variant="outline">{j.type}</Badge>
                        <span className="font-medium truncate max-w-[280px]">{j.description}</span>
                      </div>
                      <span className="text-muted-foreground">{new Date(j.createdAt).toLocaleString()}</span>
                    </div>
                    <div className="mt-1.5 grid grid-cols-2 md:grid-cols-4 gap-1 text-[10px]">
                      {j.entries.map((e) => (
                        <div key={e.accountType} className="flex justify-between">
                          <span className="text-muted-foreground">{e.accountType}</span>
                          <span className="font-mono">D ${parseFloat(e.debit).toFixed(2)} / C ${parseFloat(e.credit).toFixed(2)}</span>
                        </div>
                      ))}
                    </div>
                    <div className="mt-1 text-[10px] text-muted-foreground truncate">hash: {j.integrityHash?.slice(0, 24)}…</div>
                  </div>
                ))}
              </div>
            </ScrollArea>
          </CardContent>
        </Card>
      )}

      {tab === 'ledger' && (
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm">Ledger Entries</CardTitle></CardHeader>
          <CardContent>
            <ScrollArea className="h-96">
              <div className="space-y-1">
                {(ledger?.entries ?? []).slice(0, 200).map((e: { id: string; accountType: string; debit: string; credit: string; currency: string; createdAt: string; journal: { ref: string } }) => (
                  <div key={e.id} className="flex items-center justify-between rounded-md border px-2.5 py-1.5 text-xs">
                    <div className="flex items-center gap-2">
                      <Badge variant="outline">{e.accountType}</Badge>
                      <span className="text-muted-foreground truncate max-w-[200px]">{e.journal?.ref}</span>
                    </div>
                    <div className="flex items-center gap-3 font-mono">
                      <span className="text-muted-foreground">D ${parseFloat(e.debit).toFixed(2)}</span>
                      <span className="text-muted-foreground">C ${parseFloat(e.credit).toFixed(2)}</span>
                      <span className="text-muted-foreground">{new Date(e.createdAt).toLocaleTimeString()}</span>
                    </div>
                  </div>
                ))}
              </div>
            </ScrollArea>
          </CardContent>
        </Card>
      )}

      {tab === 'events' && (
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm">Trade Events <Badge variant="secondary" className="ml-2">immutable lifecycle</Badge></CardTitle></CardHeader>
          <CardContent>
            <ScrollArea className="h-96">
              <div className="text-[10px] text-muted-foreground mb-2">Trade events are append-only. They never update or delete.</div>
              <div className="space-y-1">
                {/* Fetch events for the account via trade-events endpoint lazily */}
                <TradeEvents accountId={accountId} />
              </div>
            </ScrollArea>
          </CardContent>
        </Card>
      )}

      {tab === 'phaseA' && (
        <Card>
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between">
              <CardTitle className="text-sm flex items-center gap-2"><CalendarCheck className="h-4 w-4" /> Phase A Observation Period</CardTitle>
              <Button size="sm" variant="outline" disabled={running} onClick={runRecon}><RefreshCw className={`h-4 w-4 mr-1 ${running ? 'animate-spin' : ''}`} /> Run Reconciliation Now</Button>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <div className="rounded-md border p-3"><div className="text-xs text-muted-foreground">Consecutive Clean Days</div><div className="text-2xl font-semibold mt-1 tabular-nums">{recon?.progress?.consecutiveCleanDays ?? 0}<span className="text-sm text-muted-foreground">/30</span></div></div>
              <div className="rounded-md border p-3"><div className="text-xs text-muted-foreground">Total Clean Observations</div><div className="text-2xl font-semibold mt-1 tabular-nums">{recon?.progress?.totalCleanObservations ?? 0}</div></div>
              <div className="rounded-md border p-3"><div className="text-xs text-muted-foreground">Today Recorded</div><div className="text-2xl font-semibold mt-1">{recon?.progress?.todayRecorded ? 'YES' : 'NO'}</div></div>
              <div className="rounded-md border p-3"><div className="text-xs text-muted-foreground">Phase A Ready</div><div className={`text-2xl font-semibold mt-1 ${recon?.progress?.phaseAReady ? 'text-emerald-600 dark:text-emerald-400' : 'text-muted-foreground'}`}>{recon?.progress?.phaseAReady ? 'YES' : 'NO'}</div></div>
            </div>
            <div>
              <div className="flex justify-between text-xs mb-1"><span className="text-muted-foreground">Progress toward 30 consecutive clean days</span><span>{recon?.progress?.consecutiveCleanDays ?? 0}/30</span></div>
              <Progress value={((recon?.progress?.consecutiveCleanDays ?? 0) / 30) * 100} />
            </div>
            <div className="rounded-md bg-muted/50 p-3 text-xs text-muted-foreground">
              A daily reconciliation runs automatically at 09:00 Africa/Nairobi (cron job 537161) and records a real dated observation. Historical simulations do not replace this period. Each day must be CLEAN (integrity valid, trial balance balanced). A single DISCREPANCY or gap resets the consecutive counter to zero.
            </div>
            <div>
              <div className="text-xs text-muted-foreground mb-2">Recent Observations</div>
              <ScrollArea className="h-48">
                <div className="space-y-1">
                  {(recon?.observations ?? []).length === 0 ? (
                    <div className="text-sm text-muted-foreground py-4 text-center">No observations yet. Run reconciliation to record today&apos;s.</div>
                  ) : (
                    (recon?.observations ?? []).slice(0, 30).map((o: { id: string; date: string; status: string; internalBalance: string; internalPositions: number; discrepancies: string | null }) => (
                      <div key={o.id} className="flex items-center justify-between rounded-md border px-2.5 py-1.5 text-xs">
                        <div className="flex items-center gap-2"><span className="font-mono">{o.date}</span><Badge variant={o.status === 'CLEAN' ? 'default' : 'destructive'}>{o.status}</Badge></div>
                        <div className="flex items-center gap-3 text-muted-foreground"><span>bal {o.internalBalance}</span><span>{o.internalPositions} pos</span></div>
                      </div>
                    ))
                  )}
                </div>
              </ScrollArea>
            </div>
          </CardContent>
        </Card>
      )}

      {tab === 'integrity' && (
        <Card>
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between">
              <CardTitle className="text-sm">Integrity Verification</CardTitle>
              <Button size="sm" variant="outline" onClick={() => refetchIntegrity()}>Re-verify</Button>
            </div>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-3 gap-3 text-center">
              <div className="rounded-md border p-3"><div className="text-xs text-muted-foreground">Checked</div><div className="text-xl font-semibold mt-1">{integrity?.checked ?? 0}</div></div>
              <div className="rounded-md border p-3 border-emerald-500/30"><div className="text-xs text-muted-foreground">Valid</div><div className="text-xl font-semibold mt-1 text-emerald-600 dark:text-emerald-400">{integrity?.valid ?? 0}</div></div>
              <div className="rounded-md border p-3 border-destructive/30"><div className="text-xs text-muted-foreground">Invalid</div><div className="text-xl font-semibold mt-1 text-destructive">{integrity?.invalid ?? 0}</div></div>
            </div>
            {integrity?.mismatches?.length > 0 && (
              <div className="mt-3 text-xs text-destructive">{integrity.mismatches.length} mismatches detected.</div>
            )}
            <div className="mt-4 rounded-md bg-muted/50 p-3 text-xs text-muted-foreground">
              Each journal stores a SHA-256 integrity hash of (id + type + sorted entries). On read, we recompute and compare.
              Append-only enforcement is repository-level in SQLite; the production PostgreSQL migration adds <code>REVOKE UPDATE, DELETE, TRUNCATE</code> on these tables.
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}

function TradeEvents({ accountId }: { accountId: string }) {
  const { data, isLoading } = useQuery({
    queryKey: ['trade-events', accountId],
    queryFn: async () => (await fetch(`/api/accounting/trade-events?accountId=${accountId}`)).json(),
  })
  if (isLoading) return <div className="text-xs text-muted-foreground">Loading…</div>
  const events = data?.events ?? []
  if (events.length === 0) return <div className="text-xs text-muted-foreground py-4 text-center">No trade events yet. Place an order to populate the lifecycle.</div>
  return (
    <>
      {events.slice(0, 200).map((e: { id: string; orderId: string; type: string; payload: string; createdAt: string; order?: { clientOrderId: string; side: string; instrument?: { symbol: string } } }) => (
        <div key={e.id} className="flex items-center justify-between rounded-md border px-2.5 py-1.5 text-xs">
          <div className="flex items-center gap-2">
            <Badge variant="outline">{e.type}</Badge>
            <span className="text-muted-foreground truncate max-w-[240px]">{e.order?.clientOrderId}</span>
          </div>
          <span className="text-muted-foreground">{new Date(e.createdAt).toLocaleTimeString()}</span>
        </div>
      ))}
    </>
  )
}
