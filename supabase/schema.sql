-- Apply in Supabase SQL editor. Backend service-role access only for MVP.
create extension if not exists pgcrypto;
create table if not exists trading_accounts (id uuid primary key default gen_random_uuid(), user_id uuid not null references auth.users(id), mode text not null default 'paper' check(mode='paper'), currency text not null default 'USD', balance numeric(20,6) not null default 10000, created_at timestamptz not null default now());
create table if not exists market_quotes (id bigint generated always as identity primary key, pair text not null, bid numeric(20,8) not null, ask numeric(20,8) not null, source text not null, observed_at timestamptz not null default now(), check(ask>=bid));
create table if not exists paper_orders (id uuid primary key default gen_random_uuid(), account_id uuid not null references trading_accounts(id), pair text not null, side text not null check(side in ('BUY','SELL')), units numeric(20,4) not null check(units>0), entry_price numeric(20,8) not null, stop_price numeric(20,8) not null, target_price numeric(20,8) not null, status text not null default 'OPEN' check(status in ('OPEN','CLOSED','REJECTED')), exit_price numeric(20,8), realized_pnl numeric(20,6), created_at timestamptz not null default now(), closed_at timestamptz);
create table if not exists agent_events (id bigint generated always as identity primary key, account_id uuid not null references trading_accounts(id), agent text not null, event_type text not null, payload jsonb not null default '{}'::jsonb, created_at timestamptz not null default now());
create table if not exists risk_settings (account_id uuid primary key references trading_accounts(id), risk_per_trade numeric(6,5) not null default .005 check(risk_per_trade>0 and risk_per_trade<=.005), daily_loss_limit numeric(6,5) not null default .02 check(daily_loss_limit>0 and daily_loss_limit<=.02), max_positions int not null default 3 check(max_positions between 1 and 3), paused boolean not null default true);
create index if not exists idx_orders_account_status on paper_orders(account_id,status);
create index if not exists idx_events_account_time on agent_events(account_id,created_at desc);
alter table trading_accounts enable row level security;
alter table market_quotes enable row level security;
alter table paper_orders enable row level security;
alter table agent_events enable row level security;
alter table risk_settings enable row level security;
create policy "read own accounts" on trading_accounts for select to authenticated using (user_id=auth.uid());
create policy "read own orders" on paper_orders for select to authenticated using (exists(select 1 from trading_accounts a where a.id=account_id and a.user_id=auth.uid()));
create policy "read own events" on agent_events for select to authenticated using (exists(select 1 from trading_accounts a where a.id=account_id and a.user_id=auth.uid()));
create policy "read own risk settings" on risk_settings for select to authenticated using (exists(select 1 from trading_accounts a where a.id=account_id and a.user_id=auth.uid()));
