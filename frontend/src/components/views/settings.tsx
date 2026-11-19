'use client'
import * as React from 'react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'
import { KeyRound, LogOut, ShieldCheck, BellRing } from 'lucide-react'

export function SettingsView({ user, onLogout }: { user: { id: string; email: string; name: string | null; role: string }; onLogout: () => void }) {
  return (
    <div className="space-y-4 max-w-3xl">
      <Card>
        <CardHeader><CardTitle className="text-sm">Profile</CardTitle><CardDescription>Your account details</CardDescription></CardHeader>
        <CardContent className="space-y-3">
          <div><Label className="text-xs">Email</Label><Input value={user.email} readOnly className="bg-muted/50" /></div>
          <div><Label className="text-xs">Name</Label><Input defaultValue={user.name || ''} placeholder="Add your name" /></div>
          <div><Label className="text-xs">Role</Label><div><Badge variant={user.role === 'ADMIN' ? 'default' : 'outline'}>{user.role}</Badge></div></div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle className="text-sm flex items-center gap-2"><KeyRound className="h-4 w-4" /> Security</CardTitle><CardDescription>Sessions & access</CardDescription></CardHeader>
        <CardContent className="space-y-3 text-sm">
          <div className="flex items-center justify-between rounded-md border p-2.5">
            <div><div className="font-medium">Active session</div><div className="text-xs text-muted-foreground">HttpOnly cookie · 7-day expiry · DB-backed revocation</div></div>
            <Badge variant="default">Active</Badge>
          </div>
          <div className="flex items-center justify-between rounded-md border p-2.5">
            <div><div className="font-medium">Password hashing</div><div className="text-xs text-muted-foreground">bcrypt (cost 12)</div></div>
            <Badge variant="secondary">Enabled</Badge>
          </div>
          <div className="flex items-center justify-between rounded-md border p-2.5">
            <div><div className="font-medium">Rate limiting</div><div className="text-xs text-muted-foreground">20 requests / 60s per IP on auth endpoints</div></div>
            <Badge variant="secondary">Enabled</Badge>
          </div>
          <Button variant="outline" onClick={onLogout}><LogOut className="h-4 w-4 mr-1" /> Sign out of all sessions</Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle className="text-sm flex items-center gap-2"><ShieldCheck className="h-4 w-4" /> Trading Authorization</CardTitle></CardHeader>
        <CardContent className="space-y-2 text-sm">
          <div className="flex items-center justify-between rounded-md border p-2.5">
            <span>LIVE trading</span>
            <Badge variant="destructive">DISABLED (fail-closed)</Badge>
          </div>
          <div className="text-xs text-muted-foreground rounded-md bg-muted/50 p-3">
            Live order routing requires Phase A, B, C acceptance + LIVE_AUTHORIZATION document + explicit human activation.
            No environment variable or single flag can enable it. See docs/PHASE_C_LIVE_READINESS.md.
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle className="text-sm flex items-center gap-2"><BellRing className="h-4 w-4" /> Notifications</CardTitle></CardHeader>
        <CardContent className="space-y-2 text-sm">
          {[
            ['Emergency stop activations', true],
            ['Daily loss limit reached', true],
            ['Drawdown threshold breached', true],
            ['Reconciliation discrepancies', true],
            ['Broker disconnections', true],
            ['Strategy backtest complete', false],
          ].map(([label, on]) => (
            <div key={label as string} className="flex items-center justify-between rounded-md border p-2.5">
              <span>{label}</span>
              <Badge variant={on ? 'default' : 'outline'}>{on ? 'On' : 'Off'}</Badge>
            </div>
          ))}
        </CardContent>
      </Card>

      <Separator />
      <div className="text-xs text-muted-foreground">
        PlayGo Trading v0.1.0-engineering · Next.js 16 + TypeScript + Prisma/SQLite · PAPER mode · {new Date().getFullYear()}
      </div>
    </div>
  )
}
