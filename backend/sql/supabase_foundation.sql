-- PlayGo AI Trading: PostgreSQL persistence foundation
-- Private schema: do not expose trading, identity or accounting records through Data API.
create schema if not exists playgo_private;
revoke all on schema playgo_private from public, anon, authenticated;
create table if not exists playgo_private.documents (
  collection_name text not null,
  document_id text not null,
  body jsonb not null,
  revision bigint not null default 0 check (revision >= 0),
  updated_at timestamptz not null default now(),
  primary key (collection_name, document_id)
);
create index if not exists playgo_documents_collection_idx
  on playgo_private.documents (collection_name);
create table if not exists playgo_private.owner_sessions (
  token_digest text primary key,
  owner_id text not null,
  expires_at timestamptz not null,
  created_at timestamptz not null default now()
);
create index if not exists playgo_owner_sessions_expiry_idx
  on playgo_private.owner_sessions (expires_at);
create table if not exists playgo_private.trade_events (
  event_id text primary key,
  trade_id text not null,
  event_type text not null,
  payload jsonb not null,
  recorded_at timestamptz not null default now()
);
create table if not exists playgo_private.accounting_journals (
  transaction_id text primary key,
  kind text not null,
  amount_cents bigint not null check (amount_cents >= 0),
  reference text not null default '',
  lines jsonb not null,
  created_at timestamptz not null default now()
);
-- No anon/authenticated grants. Application must use a server-side PostgreSQL connection.
