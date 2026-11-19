'use client'
import * as React from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useToast } from '@/hooks/use-toast'
import { CalendarDays, CheckCircle2, AlertTriangle, Lock, Play, Clock, ShieldCheck } from 'lucide-react'

export function Observation({ accountId }: { accountId: string }) {
  const qc = useQueryClient()
  const { toast } = useToast()
  const [phase, setPhase] = React.useState<'A' | 'B'>('A')

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['observation', accountId, phase],
    queryFn: async () => (await fetch(`/api/reconciliation?accountId=${accountId}&phase=${phase}`)).json(),
  })

  const { data: demo } = useQuery({
    queryKey: ['demo-broker', accountId],
    queryFn: async () => (await fetch(`/api/reconciliation/demo?accountId=${accountId}`)).json(),
    enabled: phase === 'B',
  })

  const runNow = async () => {
    const r = await fetch('/api/reconciliation/daily', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, credentials: 'include',
      body: JSON.stringify({ accountId, phase }),
    })
    const d = await r.json()
    if (!r.ok) return toast({ title: 'Error', description: d.error, variant: 'destructive' })
    toast({ title: 'Observation recorded', description: `Phase ${phase} · ${d.result?.status} · ${new Date(d.result?.date).toLocaleDateString()}` })
    qc.invalidateQueries({ queryKey: ['observation', accountId, phase] })
  }

  if (isLoading) return <div className="text-sm text-muted-foreground">Loading observation status…</div>

  const obs = data?.observation
  const isPhaseB = phase === 'B'
  const demoBlocked = isPhaseB && demo?.blocked

  return (
    <div className="space-y-4">
      <Card className="border-amber-500/30 bg-amber-500/5">
        <CardContent className="pt-6 flex items-start gap-3">
          <Clock className="h-5 w-5 text-amber-600 dark:text-amber-400 mt-0.5 shrink-0" />
          <div className="text-sm">
            <div className="font-medium">Real-world observation — cannot be simulated or fast-forwarded</div>
            <div className="text-muted-foreground mt-1">
              Per the PlayGo directive (§A10, §B8), observation periods must be measured from <strong>actual recorded observations on actual elapsed days</strong>.
              Each entry below is a real reconciliation run against the live database state on that calendar day. No past dates are back-filled; no future dates are fabricated.
              The clock accumulates one clean day per real day until the target is reached.
            </div>
          </div>
        </CardContent>
      </Card>

      <Tabs value={phase} onValueChange={(v) => setPhase(v as 'A' | 'B')}>
        <TabsList>
          <TabsTrigger value="A">Phase A — PAPER (30 days)</TabsTrigger>
          <TabsTrigger value="B">Phase B — DEMO (60 days)</TabsTrigger>
        </TabsList>
      </Tabs>

      {/* Progress */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Card className="lg:col-span-2">
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between">
              <CardTitle className="text-sm">Phase {phase} Observation Progress</CardTitle>
              <Button size="sm" onClick={runNow}><Play className="h-3.5 w-3.5 mr-1" /> Run today's reconciliation</Button>
            </div>
            <CardDescription>
              {isPhaseB ? '60 consecutive clean DEMO days required (90 recommended).' : '30 consecutive clean PAPER days required.'}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div>
              <div className="flex justify-between text-xs mb-1">
                <span className="text-muted-foreground">Clean-day streak</span>
                <span className="font-medium">{obs?.streak ?? 0} / {obs?.targetDays ?? (isPhaseB ? 60 : 30)} days</span>
              </div>
              <Progress value={obs?.progressPct ?? 0} />
              <div className="text-[10px] text-muted-foreground mt-0.5">{obs?.progressPct ?? 0}% · {obs?.remainingDays ?? (isPhaseB ? 60 : 30)} real days remaining</div>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
              <Stat label="Recorded days" value={obs?.recordedDays ?? 0} />
              <Stat label="Clean days" value={obs?.cleanDays ?? 0} accent="up" />
              <Stat label="Discrepancy days" value={obs?.discrepancyDays ?? 0} accent={obs?.discrepancyDays ? 'down' : undefined} />
              <Stat label="Complete" value={obs?.complete ? 'YES' : 'NO'} accent={obs?.complete ? 'up' : undefined} />
            </div>
            <div className="grid grid-cols-2 gap-3 text-xs">
              <div className="rounded-md border p-2">
                <div className="text-muted-foreground">First observation</div>
                <div className="font-medium mt-0.5">{obs?.firstObservation ? new Date(obs.firstObservation).toLocaleDateString() : '— not yet started'}</div>
              </div>
              <div className="rounded-md border p-2">
                <div className="text-muted-foreground">Target completion</div>
                <div className="font-medium mt-0.5">{obs?.targetDate ? new Date(obs.targetDate).toLocaleDateString() : '—'}</div>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm">Gate Status</CardTitle></CardHeader>
          <CardContent className="space-y-2 text-sm">
            <Row label="Phase target" value={`${obs?.targetDays ?? (isPhaseB ? 60 : 30)} clean days`} />
            <Row label="Current streak" value={`${obs?.streak ?? 0} days`} />
            <Row label="Discrepancies" value={obs?.discrepancyDays === 0 ? <Badge variant="default">NONE</Badge> : <Badge variant="destructive">{obs?.discrepancyDays}</Badge>} />
            <Row label="Phase status" value={obs?.complete ? <Badge variant="default">ACCEPTED</Badge> : <Badge variant="outline">IN PROGRESS</Badge>} />
            <div className="rounded-md bg-muted/50 p-2 text-[11px] text-muted-foreground mt-2">
              {obs?.complete
                ? 'Observation gate satisfied. Engineering + observation both pass for this phase.'
                : 'Observation gate NOT satisfied. Engineering is complete; only real elapsed time + clean reconciliations can close this gate.'}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Phase B DEMO broker readiness */}
      {isPhaseB && (
        <Card className={demoBlocked ? 'border-destructive/40' : ''}>
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between">
              <CardTitle className="text-sm flex items-center gap-2"><Lock className="h-4 w-4" /> DEMO Broker Readiness</CardTitle>
              <Badge variant={demoBlocked ? 'destructive' : 'default'}>{demoBlocked ? 'BLOCKED' : 'READY'}</Badge>
            </div>
          </CardHeader>
          <CardContent className="text-sm space-y-2">
            <Row label="DEMO broker configured" value={demo?.demoBroker?.configured ? 'YES' : 'NO'} />
            <Row label="WebSocket adapter implemented" value={demo?.demoBroker?.adapterImplemented ? 'YES' : 'NO (production worker required)'} />
            <Row label="DEMO connection live" value={demo?.demoBroker?.live ? 'YES' : 'NO'} />
            {demo?.brokerConnection && (
              <Row label="Broker connection record" value={<Badge variant="outline">{demo.brokerConnection.broker} · {demo.brokerConnection.status}</Badge>} />
            )}
            <div className="rounded-md bg-destructive/10 border border-destructive/30 p-2 text-xs text-destructive">
              {demo?.blockReason || 'Phase B observation cannot start.'}
            </div>
            <div className="text-xs text-muted-foreground mt-2">
              <div className="font-medium text-foreground mb-1">Requirements to start the Phase B clock:</div>
              <ol className="list-decimal list-inside space-y-0.5">
                {(demo?.requirements ?? []).map((r: string, i: number) => <li key={i}>{r}</li>)}
              </ol>
            </div>
            <div className="rounded-md border border-amber-500/30 bg-amber-500/10 p-2 text-[11px] text-amber-700 dark:text-amber-300 mt-2">
              The Deriv token in your development paste is treated as a LIVE credential and is <strong>not</strong> used for DEMO.
              Create a separate DEMO (virtual) account token at Deriv and provide it via <code>DERIV_DEMO_TOKEN</code> in server-side secret management.
            </div>
          </CardContent>
        </Card>
      )}

      {/* Observation log */}
      <Card>
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <CardTitle className="text-sm flex items-center gap-2"><CalendarDays className="h-4 w-4" /> Observation Log</CardTitle>
            <Button size="sm" variant="ghost" onClick={() => refetch()}>Refresh</Button>
          </div>
          <CardDescription>One real row per elapsed calendar day. Never back-filled.</CardDescription>
        </CardHeader>
        <CardContent>
          {(obs?.observations ?? []).length === 0 ? (
            <div className="text-sm text-muted-foreground py-8 text-center">
              <ShieldCheck className="h-8 w-8 mx-auto mb-2 opacity-40" />
              No observations recorded yet. Click <strong>Run today's reconciliation</strong> to record Day 1 now.
            </div>
          ) : (
            <ScrollArea className="h-72">
              <div className="space-y-1">
                {(obs?.observations ?? []).slice().reverse().map((o: { id: string; date: string; status: string; internalBalance: string; internalPositions: number; discrepancies: string[]; recordedAt: string }, i: number) => {
                  const dayNum = (obs?.observations ?? []).length - i
                  return (
                    <div key={o.id} className="flex items-center justify-between rounded-md border px-2.5 py-2 text-xs">
                      <div className="flex items-center gap-2">
                        <span className="text-muted-foreground w-12">Day {dayNum}</span>
                        {o.status === 'CLEAN' ? <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600 dark:text-emerald-400" /> : <AlertTriangle className="h-3.5 w-3.5 text-destructive" />}
                        <span className="font-medium">{new Date(o.date).toLocaleDateString()}</span>
                        <span className="text-muted-foreground">cash ${parseFloat(o.internalBalance).toFixed(2)} · {o.internalPositions} pos</span>
                      </div>
                      <div className="flex items-center gap-2">
                        {o.discrepancies?.length > 0 && <Badge variant="destructive">{o.discrepancies.length} issues</Badge>}
                        <Badge variant={o.status === 'CLEAN' ? 'default' : 'destructive'}>{o.status}</Badge>
                      </div>
                    </div>
                  )
                })}
              </div>
            </ScrollArea>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2"><CardTitle className="text-sm">What gets checked each day</CardTitle></CardHeader>
        <CardContent className="grid grid-cols-1 md:grid-cols-2 gap-2 text-xs">
          {[
            ['Accounting integrity (SHA-256 hash match)', true],
            ['Trial balance balances (debit = credit)', true],
            ['Internal cash balance snapshot', true],
            ['Open-position count snapshot', true],
            ['Emergency-stop state', true],
            ['Broker-side balance (Phase B, when live)', isPhaseB],
            ['Broker-side position count (Phase B, when live)', isPhaseB],
            ['Idempotent: same-day re-run updates, never duplicates', true],
          ].map(([label, on]) => (
            <div key={label as string} className="flex items-center justify-between rounded-md border px-2.5 py-1.5">
              <span>{label}</span>
              <Badge variant={on ? 'default' : 'outline'}>{on ? 'CHECKED' : 'N/A'}</Badge>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  )
}

function Stat({ label, value, accent }: { label: string; value: React.ReactNode; accent?: 'up' | 'down' }) {
  const color = accent === 'up' ? 'text-emerald-600 dark:text-emerald-400' : accent === 'down' ? 'text-destructive' : ''
  return (
    <div className="rounded-md border p-2.5">
      <div className="text-[10px] text-muted-foreground uppercase tracking-wide">{label}</div>
      <div className={`mt-0.5 text-base font-semibold tabular-nums ${color}`}>{value}</div>
    </div>
  )
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-muted-foreground">{label}</span>
      <span>{value}</span>
    </div>
  )
}
