'use client'
import * as React from 'react'
import { useQuery } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Activity, Users, Database, ScrollText } from 'lucide-react'

export function Administration() {
  const [actionFilter, setActionFilter] = React.useState('all')
  const { data } = useQuery({
    queryKey: ['admin', actionFilter],
    queryFn: async () => {
      const q = actionFilter !== 'all' ? `?action=${actionFilter}` : ''
      return (await fetch(`/api/admin/health${q}`)).json()
    },
  })
  const { data: health } = useQuery({
    queryKey: ['system-health'],
    queryFn: async () => (await fetch('/api/health')).json(),
  })

  const users = data?.users ?? []
  const accounts = data?.accounts ?? []
  const components = health?.components ?? {}
  const overallStatus = health?.status ?? 'UNKNOWN'

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <Card><CardContent className="pt-5 flex items-center justify-between">
          <div><div className="text-xs text-muted-foreground">Users</div><div className="mt-1 text-xl font-semibold">{users.length}</div></div>
          <Users className="h-5 w-5 text-muted-foreground" />
        </CardContent></Card>
        <Card><CardContent className="pt-5 flex items-center justify-between">
          <div><div className="text-xs text-muted-foreground">Trading Accounts</div><div className="mt-1 text-xl font-semibold">{accounts.length}</div></div>
          <Database className="h-5 w-5 text-muted-foreground" />
        </CardContent></Card>
        <Card><CardContent className="pt-5 flex items-center justify-between">
          <div><div className="text-xs text-muted-foreground">System Status</div><div className="mt-1 text-xl font-semibold">{overallStatus}</div></div>
          <Activity className="h-5 w-5 text-muted-foreground" />
        </CardContent></Card>
        <Card><CardContent className="pt-5 flex items-center justify-between">
          <div><div className="text-xs text-muted-foreground">LIVE Trading</div><div className="mt-1 text-xl font-semibold text-destructive">DISABLED</div></div>
        </CardContent></Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm">Users</CardTitle></CardHeader>
          <CardContent>
            <ScrollArea className="h-72">
              <div className="space-y-1">
                {users.map((u: { id: string; email: string; name: string | null; role: string; createdAt: string }) => (
                  <div key={u.id} className="flex items-center justify-between rounded-md border px-2.5 py-1.5 text-xs">
                    <div className="flex items-center gap-2">
                      <span className="font-medium">{u.email}</span>
                      {u.name && <span className="text-muted-foreground">({u.name})</span>}
                    </div>
                    <div className="flex items-center gap-2">
                      <Badge variant={u.role === 'ADMIN' ? 'default' : 'outline'}>{u.role}</Badge>
                      <span className="text-muted-foreground">{new Date(u.createdAt).toLocaleDateString()}</span>
                    </div>
                  </div>
                ))}
              </div>
            </ScrollArea>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm">Trading Accounts</CardTitle></CardHeader>
          <CardContent>
            <ScrollArea className="h-72">
              <div className="space-y-1">
                {accounts.map((a: { id: string; label: string; mode: string; broker: string; liveAuthorized: boolean; user: { email: string } }) => (
                  <div key={a.id} className="flex items-center justify-between rounded-md border px-2.5 py-1.5 text-xs">
                    <div className="flex items-center gap-2">
                      <span className="font-medium">{a.label}</span>
                      <span className="text-muted-foreground">{a.user?.email}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <Badge variant="outline">{a.mode}</Badge>
                      <Badge variant={a.liveAuthorized ? 'destructive' : 'secondary'}>{a.liveAuthorized ? 'LIVE-AUTH' : 'NO-LIVE'}</Badge>
                    </div>
                  </div>
                ))}
              </div>
            </ScrollArea>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader className="pb-2"><CardTitle className="text-sm">Component Health</CardTitle></CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
            {Object.entries(components).map(([comp, info]) => (
              <div key={comp} className="rounded-md border p-2.5 text-xs">
                <div className="flex items-center justify-between">
                  <span className="font-medium capitalize">{comp}</span>
                  <Badge variant={(info as { status: string })?.status === 'OK' ? 'default' : 'destructive'}>{(info as { status: string })?.status}</Badge>
                </div>
                <div className="text-muted-foreground mt-1 text-[10px]">{(info as { message: string })?.message}</div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <CardTitle className="text-sm flex items-center gap-2"><ScrollText className="h-4 w-4" /> Audit Log</CardTitle>
            <Select value={actionFilter} onValueChange={setActionFilter}>
              <SelectTrigger className="h-8 w-48 text-xs"><SelectValue /></SelectTrigger>
              <SelectContent>
                {['all', 'LOGIN', 'LOGOUT', 'REGISTER', 'ORDER_CREATE', 'POSITION_CLOSE', 'RISK_LIMIT_UPDATE', 'EMERGENCY_STOP_ACTIVATE', 'EMERGENCY_STOP_DEACTIVATE', 'BROKER_CONNECT', 'BROKER_REVOKE', 'STRATEGY_APPROVE', 'BACKTEST_RUN'].map(a => <SelectItem key={a} value={a}>{a}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
        </CardHeader>
        <CardContent>
          <AuditLog action={actionFilter} />
        </CardContent>
      </Card>
    </div>
  )
}

function AuditLog({ action }: { action: string }) {
  const { data, isLoading } = useQuery({
    queryKey: ['audit', action],
    queryFn: async () => {
      const q = action !== 'all' ? `?action=${action}` : ''
      return (await fetch(`/api/admin/audit${q}`)).json()
    },
  })
  if (isLoading) return <div className="text-xs text-muted-foreground">Loading…</div>
  const logs = data?.logs ?? []
  if (logs.length === 0) return <div className="text-sm text-muted-foreground py-8 text-center">No audit entries.</div>
  return (
    <ScrollArea className="h-72">
      <div className="space-y-1">
        {logs.map((l: { id: string; action: string; entity: string | null; entityId: string | null; before: string | null; after: string | null; ip: string | null; createdAt: string; user: { email: string } | null }) => (
          <div key={l.id} className="flex items-center justify-between rounded-md border px-2.5 py-1.5 text-xs">
            <div className="flex items-center gap-2">
              <Badge variant="outline">{l.action}</Badge>
              <span className="text-muted-foreground">{l.user?.email ?? 'system'}</span>
              {l.entity && <span className="text-muted-foreground">{l.entity}</span>}
            </div>
            <span className="text-muted-foreground">{new Date(l.createdAt).toLocaleString()}</span>
          </div>
        ))}
      </div>
    </ScrollArea>
  )
}
