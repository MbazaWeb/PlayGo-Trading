-- Owner identity extension for PlayGo's private PostgreSQL schema.
create table if not exists playgo_private.owners (
  owner_id text primary key,
  company_id text not null unique,
  username text not null unique,
  salt text not null,
  password_hash text not null,
  disabled boolean not null default false,
  created_at timestamptz not null default now(),
  constraint playgo_owner_company check (company_id = 'PLAYGO_TANZANIA_LIMITED')
);

-- Defense in depth against duplicate owner records, including concurrent inserts.
create unique index if not exists playgo_owner_company_unique
  on playgo_private.owners(company_id)
  where company_id = 'PLAYGO_TANZANIA_LIMITED';

alter table playgo_private.owners enable row level security;

-- Sessions must belong to an existing owner and disappear when that owner is deleted.
do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname = 'playgo_owner_session_owner_fk'
      and conrelid = 'playgo_private.owner_sessions'::regclass
  ) then
    alter table playgo_private.owner_sessions
      add constraint playgo_owner_session_owner_fk
      foreign key (owner_id) references playgo_private.owners(owner_id)
      on delete cascade;
  end if;
end
$$;

create index if not exists playgo_owner_sessions_owner_idx
  on playgo_private.owner_sessions(owner_id);
create index if not exists playgo_documents_updated_idx on playgo_private.documents(updated_at);
