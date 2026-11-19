'use client'
import * as React from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger } from '@/components/ui/alert-dialog'
import { useToast } from '@/hooks/use-toast'
import { ShieldAlert, ShieldCheck, AlertOctagon, Save } from 'lucide-react'

export function RiskCenter({ accountId }: { accountId: string }) {
  const qc = useQueryClient()
  const { toast } = useToast()
  const { data: status } = useQuery({
    queryKey: ['risk-status', accountId],
    queryFn: async () => (await fetch(`/api/risk/status?accountId=${accountId}`)).json(),
    refetchInterval: 5000,
  })
  const { data: limitsData } = useQuery({
    queryKey: ['risk-limits', accountId],
    queryFn: async () => (await fetch(`/api/risk/limits?accountId=${accountId}`)).json(),
  })
  const [form, setForm] = React.useState<Record<string, string>>({})
  const [saving, setSaving] = React.useState(false)
  const [esReason, setEsReason] = React.useState('Manual activation')

  React.useEffect(() => {
    if (limitsData?.limit) {
      const l = limitsData.limit
      setForm({
        maxPositionSize: String(l.maxPositionSize),
        maxLeverage: String(l.maxLeverage),
        maxDailyLossPct: String(l.maxDailyLossPct),
        maxWeeklyLossPct: String(l.maxWeeklyLossPct),
        maxDrawdownPct: String(l.maxDrawdownPct),
        maxAggregateExposure: String(l.maxAggregateExposure),
        maxSimultaneousPositions: String(l.maxSimultaneousPositions),
        maxSpreadPips: String(l.maxSpreadPips),
        maxSlippagePips: String(l.maxSlippagePips),
      })
    }
  }, [limitsData])

  const save = async () => {
    setSaving(true)
    try {
      const r = await fetch(`/api/risk/limits?accountId=${accountId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ accountId, ...form }),
      })
      if (!r.ok) throw new Error('Save failed')
      toast({ title: 'Risk limits updated', description: 'New versioned configuration active.' })
      qc.invalidateQueries({ queryKey: ['risk-limits', accountId] })
      qc.invalidateQueries({ queryKey: ['risk-status', accountId] })
    } catch (e) {
      toast({ title: 'Error', description: (e as Error).message, variant: 'destructive' })
    } finally {
      setSaving(false)
    }
  }

  const toggleEs = async (activate: boolean) => {
    const r = await fetch('/api/emergency-stop', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ accountId, action: activate ? 'activate' : 'deactivate', reason: esReason }),
    })
    if (!r.ok) return toast({ title: 'Error', description: 'Failed', variant: 'destructive' })
    toast({ title: activate ? 'Emergency stop ACTIVATED' : 'Emergency stop deactivated' })
    qc.invalidateQueries({ queryKey: ['risk-status', accountId] })
    qc.invalidateQueries({ queryKey: ['emergency', accountId] })
  }

  const util = status?.utilization
  const es = status?.emergencyStop

  return (
    <div className="space-y-4">
      {/* Emergency stop banner */}
      <Card className={es?.active ? 'border-destructive/50' : ''}>
        <CardContent className="pt-6">
          <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              {es?.active ? <AlertOctagon className="h-6 w-6 text-destructive" /> : <ShieldCheck className="h-6 w-6 text-emerald-600 dark:text-emerald-400" />}
              <div>
                <div className="font-medium">{es?.active ? 'Emergency Stop ACTIVE' : 'Emergency Stop Inactive'}</div>
                <div className="text-xs text-muted-foreground">
                  {es?.active ? (es.reason || 'Manual activation') + ' · since ' + (es.activatedAt ? new Date(es.activatedAt).toLocaleString() : '') : 'No active emergency stop. New entries are permitted (subject to risk checks).'}
                </div>
              </div>
            </div>
            <div className="flex items-center gap-2 w-full md:w-auto">
              {!es?.active ? (
                <>
                  <Input value={esReason} onChange={(e) => setEsReason(e.target.value)} placeholder="Reason" className="h-8 text-xs md:w-56" />
                  <AlertDialog>
                    <AlertDialogTrigger asChild>
                      <Button variant="destructive" size="sm"><AlertOctagon className="h-4 w-4 mr-1" /> Activate</Button>
                    </AlertDialogTrigger>
                    <AlertDialogContent>
                      <AlertDialogHeader><AlertDialogTitle>Activate Emergency Stop?</AlertDialogTitle>
                      <AlertDialogDescription>This immediately blocks ALL new entries on this account. Existing positions remain open. Requires explicit action to reset.</AlertDialogDescription>
                      </AlertDialogHeader>
                      <AlertDialogFooter><AlertDialogCancel>Cancel</AlertDialogCancel><AlertDialogAction onClick={() => toggleEs(true)}>Activate</AlertDialogAction></AlertDialogFooter>
                    </AlertDialogContent>
                  </AlertDialog>
                </>
              ) : (
                <AlertDialog>
                  <AlertDialogTrigger asChild><Button variant="outline" size="sm">Deactivate</Button></AlertDialogTrigger>
                  <AlertDialogContent>
                    <AlertDialogHeader><AlertDialogTitle>Deactivate Emergency Stop?</AlertDialogTitle>
                    <AlertDialogDescription>This re-enables new entries subject to all risk checks. Confirm you intend to resume trading.</AlertDialogDescription></AlertDialogHeader>
                    <AlertDialogFooter><AlertDialogCancel>Cancel</AlertDialogCancel><AlertDialogAction onClick={() => toggleEs(false)}>Deactivate</AlertDialogAction></AlertDialogFooter>
                  </AlertDialogContent>
                </AlertDialog>
              )}
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Utilization */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm flex items-center gap-2"><ShieldAlert className="h-4 w-4" /> Risk Utilization</CardTitle></CardHeader>
          <CardContent className="space-y-3 text-sm">
            <BarRow label="Aggregate Exposure" pct={util?.exposureUtilizationPct ?? 0} detail={`${util?.exposure ?? 0} / ${util?.maxAggregateExposure ?? 0}`} />
            <BarRow label="Simultaneous Positions" pct={util?.positionsUtilizationPct ?? 0} detail={`${util?.openPositions ?? 0} / ${util?.maxSimultaneousPositions ?? 0}`} />
            <div className="border-t pt-2 space-y-1">
              <div className="flex justify-between"><span className="text-muted-foreground">Net realized</span><span className={Number(util?.netRealized) < 0 ? 'text-destructive' : ''}>${util?.netRealized ?? 0}</span></div>
              <div className="flex justify-between"><span className="text-muted-foreground">Daily loss limit</span><span>${util?.dailyLossLimit ?? 0}</span></div>
              <div className="flex justify-between"><span className="text-muted-foreground">Max drawdown</span><span>${util?.drawdownLimit ?? 0}</span></div>
              <div className="flex justify-between"><span className="text-muted-foreground">Cash</span><span>${util?.cash ?? 0}</span></div>
            </div>
            {(status?.violations ?? []).length > 0 && (
              <div className="rounded-md border border-destructive/40 bg-destructive/10 p-2 text-xs text-destructive">
                Violations: {(status?.violations ?? []).join(', ')}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between">
              <CardTitle className="text-sm">Versioned Risk Limits</CardTitle>
              {limitsData?.limit && <Badge variant="outline">v{limitsData.limit.version}</Badge>}
            </div>
            <CardDescription>Changes create a new version; prior versions are retired.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2.5">
            <LimitField label="Max position size" v={form.maxPositionSize} on={(v) => setForm({ ...form, maxPositionSize: v })} />
            <LimitField label="Max leverage" v={form.maxLeverage} on={(v) => setForm({ ...form, maxLeverage: v })} />
            <div className="grid grid-cols-3 gap-2">
              <LimitField label="Daily loss %" v={form.maxDailyLossPct} on={(v) => setForm({ ...form, maxDailyLossPct: v })} />
              <LimitField label="Weekly loss %" v={form.maxWeeklyLossPct} on={(v) => setForm({ ...form, maxWeeklyLossPct: v })} />
              <LimitField label="Max DD %" v={form.maxDrawdownPct} on={(v) => setForm({ ...form, maxDrawdownPct: v })} />
            </div>
            <LimitField label="Max aggregate exposure" v={form.maxAggregateExposure} on={(v) => setForm({ ...form, maxAggregateExposure: v })} />
            <div className="grid grid-cols-3 gap-2">
              <LimitField label="Max positions" v={form.maxSimultaneousPositions} on={(v) => setForm({ ...form, maxSimultaneousPositions: v })} />
              <LimitField label="Max spread pips" v={form.maxSpreadPips} on={(v) => setForm({ ...form, maxSpreadPips: v })} />
              <LimitField label="Max slippage pips" v={form.maxSlippagePips} on={(v) => setForm({ ...form, maxSlippagePips: v })} />
            </div>
            <Button className="w-full" disabled={saving} onClick={save}><Save className="h-4 w-4 mr-1" /> {saving ? 'Saving…' : 'Save New Version'}</Button>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader className="pb-2"><CardTitle className="text-sm">Active Safeguards</CardTitle></CardHeader>
        <CardContent className="grid grid-cols-1 md:grid-cols-2 gap-2 text-sm">
          {[
            ['Emergency stop blocks new entries', true],
            ['Max position size enforcement', true],
            ['Max aggregate exposure enforcement', true],
            ['Max simultaneous positions', true],
            ['Max spread / slippage rejection', true],
            ['Daily loss limit', true],
            ['Weekly loss limit', true],
            ['Max drawdown limit', true],
            ['LIVE authorization gate (fail-closed)', true],
            ['Market-hours check (FX weekends)', true],
            ['Order idempotency (clientOrderId)', true],
            ['Append-only accounting & trade events', true],
          ].map(([label, ok]) => (
            <div key={label as string} className="flex items-center justify-between rounded-md border px-2.5 py-1.5 text-xs">
              <span>{label}</span>
              <Badge variant={ok ? 'default' : 'destructive'}>{ok ? 'ENABLED' : 'OFF'}</Badge>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  )
}

function BarRow({ label, pct, detail }: { label: string; pct: number; detail: string }) {
  return (
    <div>
      <div className="flex justify-between text-xs mb-1"><span className="text-muted-foreground">{label}</span><span>{detail}</span></div>
      <Progress value={Math.min(100, pct)} className={pct > 90 ? '[&>div]:bg-destructive' : ''} />
      <div className="text-[10px] text-muted-foreground mt-0.5">{pct.toFixed(1)}% utilized</div>
    </div>
  )
}

function LimitField({ label, v, on }: { label: string; v?: string; on: (v: string) => void }) {
  return (
    <div>
      <Label className="text-xs">{label}</Label>
      <Input value={v ?? ''} onChange={(e) => on(e.target.value)} className="h-8 text-xs" inputMode="decimal" />
    </div>
  )
}
