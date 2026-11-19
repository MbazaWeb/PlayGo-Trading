'use client'
import * as React from 'react'
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query'
import { LayoutDashboard, CandlestickChart, BrainCog, Wallet, ShieldAlert, BookOpen, Plug, Settings2, Settings, LogOut, Activity, AlertTriangle, Sun, Moon, CalendarClock } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { useTheme } from 'next-themes'
import { AuthView } from '@/components/views/auth'
import { Dashboard } from '@/components/views/dashboard'
import { TradingTerminal } from '@/components/views/trading-terminal'
import { StrategyCenter } from '@/components/views/strategy-center'
import { Portfolio } from '@/components/views/portfolio'
import { RiskCenter } from '@/components/views/risk-center'
import { Accounting } from '@/components/views/accounting'
import { BrokerConnections } from '@/components/views/broker-connections'
import { Administration } from '@/components/views/administration'
import { SettingsView } from '@/components/views/settings'
import { Observation } from '@/components/views/observation'

const qc = new QueryClient({ defaultOptions: { queries: { refetchOnWindowFocus: false, retry: 1 } } })

export type ViewKey =
  | 'dashboard' | 'terminal' | 'strategies' | 'portfolio'
  | 'risk' | 'accounting' | 'brokers' | 'observation' | 'admin' | 'settings'

const NAV: { key: ViewKey; label: string; icon: React.ElementType }[] = [
  { key: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { key: 'terminal', label: 'Trading Terminal', icon: CandlestickChart },
  { key: 'strategies', label: 'Strategy Center', icon: BrainCog },
  { key: 'portfolio', label: 'Portfolio', icon: Wallet },
  { key: 'risk', label: 'Risk Center', icon: ShieldAlert },
  { key: 'accounting', label: 'Accounting', icon: BookOpen },
  { key: 'brokers', label: 'Broker Connections', icon: Plug },
  { key: 'observation', label: 'Observation (Phase A/B)', icon: CalendarClock },
  { key: 'admin', label: 'Administration', icon: Settings2 },
  { key: 'settings', label: 'Settings', icon: Settings },
]

function useMe() {
  return useQuery({
    queryKey: ['me'],
    queryFn: async () => {
      const r = await fetch('/api/auth/me', { credentials: 'include' })
      if (!r.ok) return { user: null, account: null }
      return r.json()
    },
  })
}

function ThemeToggle() {
  const { theme, setTheme } = useTheme()
  const [mounted, setMounted] = React.useState(false)
  React.useEffect(() => setMounted(true), [])
  if (!mounted) return <div className="w-9 h-9" />
  const isDark = theme === 'dark'
  return (
    <Button variant="ghost" size="icon" onClick={() => setTheme(isDark ? 'light' : 'dark')} aria-label="Toggle theme">
      {isDark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
    </Button>
  )
}

function Shell() {
  const { data, isLoading, refetch } = useMe()
  const [view, setView] = React.useState<ViewKey>('dashboard')
  const user = data?.user
  const account = data?.account
  const [accountId, setAccountId] = React.useState<string | null>(account?.id ?? null)
  React.useEffect(() => {
    if (account && !accountId) setAccountId(account.id)
  }, [account, accountId])

  const logout = async () => {
    await fetch('/api/auth/logout', { method: 'POST', credentials: 'include' })
    setAccountId(null)
    await refetch()
  }

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="text-muted-foreground text-sm">Loading PlayGo Trading…</div>
      </div>
    )
  }

  if (!user) {
    return (
      <div className="min-h-screen flex flex-col bg-background">
        <AuthView onAuthed={() => refetch()} />
        <Footer />
      </div>
    )
  }

  const navItems = user.role === 'ADMIN' ? NAV : NAV.filter(n => n.key !== 'admin')

  return (
    <div className="min-h-screen flex flex-col bg-background">
      <div className="flex flex-1 min-h-0">
        {/* Sidebar */}
        <aside className="hidden md:flex w-60 shrink-0 flex-col border-r bg-sidebar text-sidebar-foreground">
          <div className="h-14 flex items-center gap-2 px-4 border-b">
            <div className="h-7 w-7 rounded-md bg-primary text-primary-foreground flex items-center justify-center text-xs font-bold">PG</div>
            <div className="font-semibold tracking-tight">PlayGo Trading</div>
          </div>
          <nav className="flex-1 overflow-y-auto p-2 space-y-1">
            {navItems.map(item => {
              const Icon = item.icon
              return (
                <button
                  key={item.key}
                  onClick={() => setView(item.key)}
                  className={cn(
                    'w-full flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors',
                    view === item.key ? 'bg-sidebar-accent text-sidebar-accent-foreground' : 'hover:bg-sidebar-accent/60'
                  )}
                >
                  <Icon className="h-4 w-4 shrink-0" />
                  <span className="truncate">{item.label}</span>
                </button>
              )
            })}
          </nav>
          <div className="border-t p-3 space-y-2">
            <div className="text-xs text-muted-foreground truncate">{user.email}</div>
            <Button variant="outline" size="sm" className="w-full" onClick={logout}>
              <LogOut className="h-4 w-4 mr-2" /> Sign out
            </Button>
          </div>
        </aside>

        {/* Main */}
        <div className="flex-1 flex flex-col min-w-0">
          {/* Top bar */}
          <header className="h-14 flex items-center gap-3 border-b px-4 bg-background">
            <div className="md:hidden font-semibold">PlayGo</div>
            <div className="hidden md:block text-sm text-muted-foreground">
              {NAV.find(n => n.key === view)?.label}
            </div>
            <div className="ml-auto flex items-center gap-2">
              <Badge variant="secondary" className="gap-1">
                <Activity className="h-3 w-3" /> PAPER
              </Badge>
              {account && (
                <Badge variant={account.mode === 'LIVE' ? 'destructive' : 'outline'} className="gap-1">
                  {account.mode === 'LIVE' && <AlertTriangle className="h-3 w-3" />}
                  {account.mode}
                </Badge>
              )}
              <ThemeToggle />
            </div>
          </header>

          {/* Mobile nav */}
          <div className="md:hidden border-b px-2 py-2 flex gap-1 overflow-x-auto bg-background">
            {navItems.map(item => {
              const Icon = item.icon
              return (
                <button
                  key={item.key}
                  onClick={() => setView(item.key)}
                  className={cn(
                    'flex items-center gap-1 rounded-md px-2.5 py-1.5 text-xs whitespace-nowrap',
                    view === item.key ? 'bg-primary text-primary-foreground' : 'bg-muted hover:bg-muted/70'
                  )}
                >
                  <Icon className="h-3.5 w-3.5" /> {item.label}
                </button>
              )
            })}
          </div>

          <main className="flex-1 overflow-y-auto p-4 md:p-6">
            <ViewRouter
              view={view}
              user={user}
              accountId={accountId}
              setAccountId={setAccountId}
              onLogout={logout}
            />
          </main>
        </div>
      </div>
      <Footer />
    </div>
  )
}

function ViewRouter(props: { view: ViewKey; user: { id: string; email: string; name: string | null; role: string }; accountId: string | null; setAccountId: (id: string) => void; onLogout: () => void }) {
  const { view, user, accountId, setAccountId, onLogout } = props
  if (!accountId) {
    return <div className="text-sm text-muted-foreground">No trading account. Sign out and register again to provision one.</div>
  }
  switch (view) {
    case 'dashboard': return <Dashboard accountId={accountId} />
    case 'terminal': return <TradingTerminal accountId={accountId} />
    case 'strategies': return <StrategyCenter />
    case 'portfolio': return <Portfolio accountId={accountId} />
    case 'risk': return <RiskCenter accountId={accountId} />
    case 'accounting': return <Accounting accountId={accountId} />
    case 'brokers': return <BrokerConnections accountId={accountId} />
    case 'observation': return <Observation accountId={accountId} />
    case 'admin': return user.role === 'ADMIN' ? <Administration /> : <Dashboard accountId={accountId} />
    case 'settings': return <SettingsView user={user} onLogout={onLogout} />
    default: return <Dashboard accountId={accountId} />
  }
}

function Footer() {
  return (
    <footer className="mt-auto border-t bg-background px-4 py-3 text-xs text-muted-foreground">
      <div className="flex flex-col md:flex-row items-center justify-between gap-2 max-w-7xl mx-auto">
        <div className="flex items-center gap-2">
          <span className="font-medium text-foreground">PlayGo Trading</span>
          <span>·</span>
          <span>PAPER mode — synthetic market data</span>
          <span>·</span>
          <span>LIVE trading disabled (fail-closed)</span>
        </div>
        <div className="flex items-center gap-3">
          <span>v0.1.0-engineering</span>
          <span>·</span>
          <span>Rotate credentials before going live</span>
        </div>
      </div>
    </footer>
  )
}

export function AppShell() {
  return (
    <QueryClientProvider client={qc}>
      <Shell />
    </QueryClientProvider>
  )
}
