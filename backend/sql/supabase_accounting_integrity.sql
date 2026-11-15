-- Enforce a single reversal per original paper journal.
create unique index if not exists playgo_accounting_single_reversal
  on playgo_private.accounting_journals(reference) where kind='REVERSAL';
create index if not exists playgo_accounting_journals_created
  on playgo_private.accounting_journals(created_at desc);
