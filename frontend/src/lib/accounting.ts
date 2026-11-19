// accounting.ts — Double-entry accounting engine (append-only).
//
// Rules enforced here (the DB-role enforcement is documented for PostgreSQL):
//   1. Every journal has a unique `ref` (idempotency key).
//   2. Every journal MUST balance: sum(debit) === sum(credit).
//   3. Journals and trade events are NEVER updated or deleted.
//   4. An integrity hash is computed and stored on each journal.
//
// Account types (chart of accounts):
//   CASH              — liquid cash (debit balance)
//   CAPITAL           — owner's capital (credit balance)
//   CLIENT_LIABILITY  — open positions liability to client (offsets unrealized)
//   REALIZED_PNL      — realized profit/loss
//   UNREALIZED_PNL    — mark-to-market unrealized P&L
//   COMMISSION        — broker commission (debit)
//   SWAP              — financing/swap charges (debit)
//   FEES              — other fees (debit)
import { db } from '@/lib/db'
import { Decimal } from 'decimal.js'
import { D, ledgerBalances, hashJournal, zero, round, add, sub } from '@/lib/money'
import { audit } from '@/lib/audit'

export type LedgerAccountType =
  | 'CASH' | 'CAPITAL' | 'CLIENT_LIABILITY'
  | 'REALIZED_PNL' | 'UNREALIZED_PNL'
  | 'COMMISSION' | 'SWAP' | 'FEES'

export type EntryInput = {
  accountType: LedgerAccountType
  debit?: string | number | Decimal
  credit?: string | number | Decimal
}

export type PostJournalInput = {
  tradingAccountId: string
  ref: string
  type: 'OPENING_CAPITAL' | 'TRADE' | 'FEE' | 'COMMISSION' | 'SWAP' | 'DEPOSIT' | 'WITHDRAWAL' | 'ADJUSTMENT' | 'REALIZED_PNL' | 'UNREALIZED_PNL'
  description: string
  entries: EntryInput[]
  userId?: string
}

// Verify entries balance BEFORE posting. Throws if not.
function assertBalanced(entries: EntryInput[]) {
  const { debit, credit, balanced } = ledgerBalances(
    entries.map(e => ({ debit: e.debit ?? 0, credit: e.credit ?? 0 }))
  )
  if (!balanced) {
    throw new Error(`Journal does not balance: debit=${debit.toString()} credit=${credit.toString()}`)
  }
}

// Idempotent post: if a journal with this `ref` already exists, return it
// without creating a duplicate.
export async function postJournal(input: PostJournalInput) {
  assertBalanced(input.entries)
  const existing = await db.accountingJournal.findUnique({ where: { ref: input.ref } })
  if (existing) {
    return db.accountingJournal.findUnique({
      where: { id: existing.id },
      include: { entries: true },
    })
  }
  const created = await db.accountingJournal.create({
    data: {
      tradingAccountId: input.tradingAccountId,
      ref: input.ref,
      type: input.type,
      description: input.description,
      integrityHash: 'pending',
    },
  })
  const entriesData = input.entries.map(e => ({
    journalId: created.id,
    accountType: e.accountType,
    debit: round(e.debit ?? 0, 6).toString(),
    credit: round(e.credit ?? 0, 6).toString(),
    currency: 'USD',
  }))
  await db.ledgerEntry.createMany({ data: entriesData })
  const hash = hashJournal(created.id, input.type, entriesData)
  // Integrity hash is written ONCE. Append-only: we never update financial
  // fields after this. Writing the hash immediately after creation is the
  // only permitted write to a journal row.
  await db.accountingJournal.update({ where: { id: created.id }, data: { integrityHash: hash } })
  await audit({
    userId: input.userId,
    action: 'JOURNAL_POST',
    entity: 'AccountingJournal',
    entityId: created.id,
    after: { ref: input.ref, type: input.type },
  })
  return db.accountingJournal.findUnique({ where: { id: created.id }, include: { entries: true } })
}

// Compute the current cash balance for an account.
export async function cashBalance(tradingAccountId: string): Promise<Decimal> {
  const rows = await db.ledgerEntry.findMany({
    where: { journal: { tradingAccountId }, accountType: 'CASH' },
  })
  const debit = rows.reduce((s, r) => s.plus(D(r.debit)), zero())
  const credit = rows.reduce((s, r) => s.plus(D(r.credit)), zero())
  return round(sub(debit, credit), 2)
}

// Compute realized P&L (credit balance account: realizedPnl = credit - debit).
export async function realizedPnl(tradingAccountId: string): Promise<Decimal> {
  const rows = await db.ledgerEntry.findMany({
    where: { journal: { tradingAccountId }, accountType: 'REALIZED_PNL' },
  })
  const debit = rows.reduce((s, r) => s.plus(D(r.debit)), zero())
  const credit = rows.reduce((s, r) => s.plus(D(r.credit)), zero())
  return round(sub(credit, debit), 2)
}

// Compute total commissions paid (debit account).
export async function totalFees(tradingAccountId: string): Promise<Decimal> {
  const types = ['COMMISSION', 'SWAP', 'FEES'] as const
  let total = zero()
  for (const t of types) {
    const rows = await db.ledgerEntry.findMany({
      where: { journal: { tradingAccountId }, accountType: t },
    })
    const debit = rows.reduce((s, r) => s.plus(D(r.debit)), zero())
    const credit = rows.reduce((s, r) => s.plus(D(r.credit)), zero())
    total = add(total, sub(debit, credit))
  }
  return round(total, 2)
}

// Opening capital journal — posts USD 10,000 to CASH and CAPITAL.
// Idempotent via ref. Safe to call on every startup.
export async function postOpeningCapital(tradingAccountId: string, amount = '10000.00', userId?: string) {
  return postJournal({
    tradingAccountId,
    ref: `opening-capital:${tradingAccountId}`,
    type: 'OPENING_CAPITAL',
    description: `Opening paper capital USD ${amount}`,
    entries: [
      { accountType: 'CASH', debit: amount, credit: '0' },
      { accountType: 'CAPITAL', debit: '0', credit: amount },
    ],
    userId,
  })
}

// Post a trade settlement: cash movement, commission, realized P&L on close.
export async function postTradeSettlement(input: {
  tradingAccountId: string
  ref: string
  description: string
  cashDelta: Decimal // negative = cash out (buy), positive = cash in (sell/close)
  commission: Decimal
  swap: Decimal
  realizedPnl: Decimal // positive = profit
  userId?: string
}) {
  const { cashDelta, commission, swap, realizedPnl } = input
  // Double-entry must balance. We post CASH movement + commission + swap + realized P&L.
  // For a BUY (cash out): CASH credit = |cashDelta|, offset by CLIENT_LIABILITY debit.
  // For a CLOSE: CASH debit = proceeds, REALIZED_PNL credit = profit (or debit if loss),
  //              offsetting CLIENT_LIABILITY credit.
  // To keep it general and always balanced, we compute entries as follows:
  //   CASH         debit/credit = |cashDelta|
  //   COMMISSION   debit = commission
  //   SWAP         debit = swap
  //   REALIZED_PNL credit = realizedPnl (if profit), debit = -realizedPnl (if loss)
  //   CLIENT_LIABILITY balancing leg
  const entries: EntryInput[] = []
  const absCash = cashDelta.abs()
  if (cashDelta.gte(0)) {
    entries.push({ accountType: 'CASH', debit: absCash, credit: '0' })
  } else {
    entries.push({ accountType: 'CASH', debit: '0', credit: absCash })
  }
  if (commission.gt(0)) entries.push({ accountType: 'COMMISSION', debit: commission, credit: '0' })
  if (swap.gt(0)) entries.push({ accountType: 'SWAP', debit: swap, credit: '0' })
  if (realizedPnl.gte(0)) {
    entries.push({ accountType: 'REALIZED_PNL', debit: '0', credit: realizedPnl })
  } else {
    entries.push({ accountType: 'REALIZED_PNL', debit: realizedPnl.abs(), credit: '0' })
  }
  // Compute balancing leg on CLIENT_LIABILITY.
  const debit = entries.reduce((s, e) => s.plus(D(e.debit ?? 0)), zero())
  const credit = entries.reduce((s, e) => s.plus(D(e.credit ?? 0)), zero())
  const diff = sub(debit, credit)
  if (diff.gt(0)) {
    entries.push({ accountType: 'CLIENT_LIABILITY', debit: '0', credit: diff })
  } else if (diff.lt(0)) {
    entries.push({ accountType: 'CLIENT_LIABILITY', debit: diff.abs(), credit: '0' })
  }
  return postJournal({
    tradingAccountId: input.tradingAccountId,
    ref: input.ref,
    type: 'TRADE',
    description: input.description,
    entries,
    userId: input.userId,
  })
}

// Verify integrity of all journals for an account (hash matches recomputed).
export async function verifyIntegrity(tradingAccountId: string): Promise<{ checked: number; valid: number; invalid: number; mismatches: { journalId: string; expected: string; actual: string }[] }> {
  const journals = await db.accountingJournal.findMany({
    where: { tradingAccountId },
    include: { entries: true },
  })
  let valid = 0, invalid = 0
  const mismatches: { journalId: string; expected: string; actual: string }[] = []
  for (const j of journals) {
    const expected = hashJournal(j.id, j.type, j.entries.map(e => ({ accountType: e.accountType, debit: e.debit, credit: e.credit })))
    if (expected === j.integrityHash) {
      valid++
    } else {
      invalid++
      mismatches.push({ journalId: j.id, expected, actual: j.integrityHash ?? '' })
    }
  }
  return { checked: journals.length, valid, invalid, mismatches }
}

// Append-only guard: explicitly reject any update/delete attempt.
// This is called by all repository functions that touch journals/events.
export function assertAppendOnly(table: 'AccountingJournal' | 'TradeEvent', op: 'update' | 'delete') {
  throw new Error(`APPEND-ONLY VIOLATION: ${op} on ${table} is forbidden by financial integrity policy.`)
}

// Verify that the ledger balances across the whole account:
// sum(debit across all entries) === sum(credit across all entries).
export async function trialBalance(tradingAccountId: string): Promise<{ debit: Decimal; credit: Decimal; balanced: boolean }> {
  const rows = await db.ledgerEntry.findMany({ where: { journal: { tradingAccountId } } })
  const debit = rows.reduce((s, r) => s.plus(D(r.debit)), zero())
  const credit = rows.reduce((s, r) => s.plus(D(r.credit)), zero())
  return { debit: round(debit, 2), credit: round(credit, 2), balanced: debit.eq(credit) }
}
