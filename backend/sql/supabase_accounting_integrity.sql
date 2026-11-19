-- Enforce a single reversal per original paper journal.
create unique index if not exists playgo_accounting_single_reversal
  on playgo_private.accounting_journals(reference) where kind='REVERSAL';
create index if not exists playgo_accounting_journals_created
  on playgo_private.accounting_journals(created_at desc);

-- Corrections are additional journal entries. Preserve the original audit rows.
create or replace function playgo_private.reject_audit_mutation()
returns trigger
language plpgsql
set search_path = pg_catalog
as $$
begin
  raise exception 'Paper audit records are append-only'
    using errcode = '42501';
end;
$$;

create or replace trigger playgo_trade_events_append_only
  before update or delete or truncate on playgo_private.trade_events
  for each statement execute function playgo_private.reject_audit_mutation();

create or replace trigger playgo_accounting_journals_append_only
  before update or delete or truncate on playgo_private.accounting_journals
  for each statement execute function playgo_private.reject_audit_mutation();
