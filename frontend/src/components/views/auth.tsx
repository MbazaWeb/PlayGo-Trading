'use client'
import * as React from 'react'
import { useToast } from '@/hooks/use-toast'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { AlertTriangle, ShieldCheck } from 'lucide-react'

export function AuthView({ onAuthed }: { onAuthed: () => void }) {
  const { toast } = useToast()
  const [username, setUsername] = React.useState('')
  const [password, setPassword] = React.useState('')
  const [loading, setLoading] = React.useState(false)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    try {
      const r = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ username, password }),
      })
      const data = await r.json()
      if (!r.ok) throw new Error(data.error || 'Authentication failed')
      toast({ title: 'Signed in', description: 'PlayGo owner' })
      onAuthed()
    } catch (e) {
      toast({ title: 'Error', description: (e as Error).message, variant: 'destructive' })
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex-1 flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        <div className="text-center mb-6">
          <div className="inline-flex h-12 w-12 items-center justify-center rounded-xl bg-primary text-primary-foreground font-bold text-lg mb-3">PG</div>
          <h1 className="text-2xl font-semibold tracking-tight">PlayGo Trading</h1>
          <p className="text-sm text-muted-foreground mt-1">Production-engineered algorithmic trading platform</p>
        </div>
        <Card>
          <CardHeader>
            <CardTitle className="text-base mt-1">Owner sign in</CardTitle>
            <CardDescription className="mt-1">PAPER mode only. No real-money trading.</CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={submit} className="space-y-4">
              <div className="space-y-1.5">
                <Label htmlFor="username">Owner username</Label>
                <Input id="username" value={username} onChange={(e) => setUsername(e.target.value)} required placeholder="owner" />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="password">Password</Label>
                <Input id="password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} required placeholder="••••••••••••" />
              </div>
              <Button type="submit" className="w-full" disabled={loading}>
                {loading ? 'Please wait…' : 'Sign in'}
              </Button>
            </form>
            <div className="mt-4 rounded-md border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-700 dark:text-amber-300 flex gap-2">
              <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
              <div>
                This environment uses <strong>synthetic PAPER market data</strong>. LIVE broker trading is
                <strong> fail-closed</strong> and requires explicit human authorization per the governance directive.
              </div>
            </div>
            <div className="mt-3 rounded-md border border-emerald-500/30 bg-emerald-500/10 p-3 text-xs text-emerald-700 dark:text-emerald-300 flex gap-2">
              <ShieldCheck className="h-4 w-4 shrink-0 mt-0.5" />
              <div>Append-only accounting journals, immutable trade events, double-entry ledger, integrity-hash verification.</div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
