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
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger } from '@/components/ui/alert-dialog'
import { useToast } from '@/hooks/use-toast'
import { Plug, Trash2, ShieldAlert, Lock } from 'lucide-react'

const BROKERS = [
  { value: 'PAPER', label: 'PAPER (synthetic)', mode: 'PAPER' },
  { value: 'DERIV_DEMO', label: 'Deriv — Demo', mode: 'DEMO' },
  { value: 'DERIV_LIVE', label: 'Deriv — LIVE (gated)', mode: 'LIVE' },
  { value: 'OANDA_PRACTICE', label: 'OANDA — Practice', mode: 'DEMO' },
]

export function BrokerConnections({ accountId }: { accountId: string }) {
  const qc = useQueryClient()
  const { toast } = useToast()
  const { data } = useQuery({
    queryKey: ['broker-conns', accountId],
    queryFn: async () => (await fetch(`/api/broker/connections?accountId=${accountId}`)).json(),
  })
  const [broker, setBroker] = React.useState('DERIV_DEMO')
  const [mode, setMode] = React.useState('DEMO')
  const [accountRef, setAccountRef] = React.useState('')

  const connect = async () => {
    const def = BROKERS.find(b => b.value === broker)
    const r = await fetch('/api/broker/connections', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ accountId, broker, mode: mode || def?.mode || 'DEMO', accountRef }),
    })
    const d = await r.json()
    if (!r.ok) return toast({ title: 'Error', description: d.error, variant: 'destructive' })
    toast({ title: 'Broker connected', description: `${broker} · ${d.connection.permissions}` })
    qc.invalidateQueries({ queryKey: ['broker-conns', accountId] })
    setAccountRef('')
  }

  const revoke = async (id: string) => {
    const r = await fetch(`/api/broker/connections?id=${id}`, { method: 'DELETE', credentials: 'include' })
    if (!r.ok) return toast({ title: 'Error', description: 'Revoke failed', variant: 'destructive' })
    toast({ title: 'Connection revoked' })
    qc.invalidateQueries({ queryKey: ['broker-conns', accountId] })
  }

  const conns = data?.connections ?? []

  return (
    <div className="space-y-4">
      <Card className="border-amber-500/30 bg-amber-500/5">
        <CardContent className="pt-6 flex items-start gap-3">
          <ShieldAlert className="h-5 w-5 text-amber-600 dark:text-amber-400 mt-0.5" />
          <div className="text-sm">
            <div className="font-medium">LIVE trading is fail-closed</div>
            <div className="text-muted-foreground mt-1">
              Connecting a LIVE broker grants READ permissions only. Real-money order routing requires Phase A, B, C
              acceptance, a completed LIVE_AUTHORIZATION document, and explicit human activation. No single flag enables live trading.
            </div>
          </div>
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Card className="lg:col-span-1">
          <CardHeader><CardTitle className="text-sm">Connect Broker</CardTitle><CardDescription>Record-only; no secrets stored in frontend.</CardDescription></CardHeader>
          <CardContent className="space-y-3">
            <div>
              <Label className="text-xs">Broker</Label>
              <Select value={broker} onValueChange={(v) => { setBroker(v); const def = BROKERS.find(b => b.value === v); setMode(def?.mode || 'DEMO') }}>
                <SelectTrigger className="h-8 text-xs"><SelectValue /></SelectTrigger>
                <SelectContent>{BROKERS.map(b => <SelectItem key={b.value} value={b.value}>{b.label}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div>
              <Label className="text-xs">Mode</Label>
              <Select value={mode} onValueChange={setMode}>
                <SelectTrigger className="h-8 text-xs"><SelectValue /></SelectTrigger>
                <SelectContent>{['PAPER', 'DEMO', 'LIVE'].map(m => <SelectItem key={m} value={m}>{m}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div>
              <Label className="text-xs">Account reference (not a secret)</Label>
              <Input value={accountRef} onChange={(e) => setAccountRef(e.target.value)} placeholder="e.g. CR-12345 (read-only)" className="h-8 text-xs" />
            </div>
            <Button className="w-full" onClick={connect}><Plug className="h-4 w-4 mr-1" /> Connect</Button>
            <div className="text-[10px] text-muted-foreground">
              Broker credentials (API tokens) must be stored in server-side secret management, never in the database in plaintext, never in frontend code.
            </div>
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader className="pb-2"><CardTitle className="text-sm">Connections</CardTitle></CardHeader>
          <CardContent>
            <ScrollArea className="h-96">
              <div className="space-y-2">
                {conns.length === 0 ? <div className="text-sm text-muted-foreground py-8 text-center">No broker connections.</div> :
                conns.map((c: { id: string; broker: string; mode: string; status: string; permissions: string; accountRef: string | null; lastCheckedAt: string | null; createdAt: string }) => (
                  <div key={c.id} className="rounded-md border p-3 text-xs">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <Badge variant="outline">{c.broker}</Badge>
                        <Badge variant="secondary">{c.mode}</Badge>
                        {c.mode === 'LIVE' && <Lock className="h-3.5 w-3.5 text-amber-600 dark:text-amber-400" />}
                      </div>
                      <div className="flex items-center gap-2">
                        <Badge variant={c.status === 'CONNECTED' ? 'default' : c.status === 'REVOKED' ? 'destructive' : 'outline'}>{c.status}</Badge>
                        <AlertDialog>
                          <AlertDialogTrigger asChild><Button size="sm" variant="ghost"><Trash2 className="h-3.5 w-3.5" /></Button></AlertDialogTrigger>
                          <AlertDialogContent>
                            <AlertDialogHeader><AlertDialogTitle>Revoke connection?</AlertDialogTitle>
                            <AlertDialogDescription>This sets the connection to REVOKED and downgrades permissions to READ.</AlertDialogDescription></AlertDialogHeader>
                            <AlertDialogFooter><AlertDialogCancel>Cancel</AlertDialogCancel><AlertDialogAction onClick={() => revoke(c.id)}>Revoke</AlertDialogAction></AlertDialogFooter>
                          </AlertDialogContent>
                        </AlertDialog>
                      </div>
                    </div>
                    <div className="mt-1.5 grid grid-cols-2 gap-1 text-muted-foreground">
                      <div>Account: {c.accountRef || '—'}</div>
                      <div>Permissions: {c.permissions}</div>
                      <div>Last checked: {c.lastCheckedAt ? new Date(c.lastCheckedAt).toLocaleString() : '—'}</div>
                      <div>Connected: {new Date(c.createdAt).toLocaleString()}</div>
                    </div>
                  </div>
                ))}
              </div>
            </ScrollArea>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
