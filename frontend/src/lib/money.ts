// money.ts — Decimal-safe monetary calculations.
// Binary floating-point is NEVER used for authoritative balances.
import { Decimal } from 'decimal.js'

Decimal.set({ precision: 28, rounding: Decimal.ROUND_HALF_UP })

export const D = (v: Decimal.Value | null | undefined): Decimal => {
  if (v === null || v === undefined) return new Decimal(0)
  return new Decimal(v)
}

export const add = (a: Decimal.Value, b: Decimal.Value): Decimal => D(a).plus(D(b))
export const sub = (a: Decimal.Value, b: Decimal.Value): Decimal => D(a).minus(D(b))
export const mul = (a: Decimal.Value, b: Decimal.Value): Decimal => D(a).times(D(b))
export const div = (a: Decimal.Value, b: Decimal.Value): Decimal => {
  const bv = D(b)
  if (bv.isZero()) throw new Error('Division by zero')
  return D(a).div(bv)
}

export const cmp = (a: Decimal.Value, b: Decimal.Value): number => D(a).cmp(D(b))
export const gt = (a: Decimal.Value, b: Decimal.Value): boolean => D(a).gt(D(b))
export const gte = (a: Decimal.Value, b: Decimal.Value): boolean => D(a).gte(D(b))
export const lt = (a: Decimal.Value, b: Decimal.Value): boolean => D(a).lt(D(b))
export const lte = (a: Decimal.Value, b: Decimal.Value): boolean => D(a).lte(D(b))
export const abs = (a: Decimal.Value): Decimal => D(a).abs()
export const neg = (a: Decimal.Value): Decimal => D(a).negated()

// Round to a fixed number of decimal places (default 2 for currency).
export const round = (a: Decimal.Value, dp = 2): Decimal => D(a).toDecimalPlaces(dp, Decimal.ROUND_HALF_UP)
// Round to pip size for prices.
export const toPip = (price: Decimal.Value, pipSize: Decimal.Value): Decimal =>
  D(price).toDecimalPlaces(D(pipSize).decimalPlaces(), Decimal.ROUND_HALF_UP)

// Format a monetary value with thousand separators and a fixed number of
// decimal places. (decimal.js v10's default build does not ship `toFormat`,
// so we format via `toFixed` + a grouping regex to avoid a runtime crash.)
export const fmtMoney = (a: Decimal.Value, dp = 2): string => {
  const fixed = D(a).toFixed(dp)
  const neg = fixed.startsWith('-')
  const body = neg ? fixed.slice(1) : fixed
  const [intPart, decPart] = body.split('.')
  const grouped = intPart.replace(/\B(?=(\d{3})+(?!\d))/g, ',')
  const out = decPart !== undefined ? `${grouped}.${decPart}` : grouped
  return neg ? `-${out}` : out
}

export const fmtPrice = (a: Decimal.Value, precision = 5): string =>
  D(a).toFixed(precision)

export const zero = (): Decimal => new Decimal(0)

// Verify a set of ledger entries balances: sum(debit) === sum(credit)
export const ledgerBalances = (
  entries: { debit: Decimal.Value; credit: Decimal.Value }[]
): { debit: Decimal; credit: Decimal; balanced: boolean } => {
  const debit = entries.reduce((s, e) => s.plus(D(e.debit)), zero())
  const credit = entries.reduce((s, e) => s.plus(D(e.credit)), zero())
  return { debit, credit, balanced: debit.eq(credit) }
}

export const hashJournal = (
  journalId: string,
  type: string,
  entries: { accountType: string; debit: Decimal.Value; credit: Decimal.Value }[]
): string => {
  const payload = journalId + '|' + type + '|' + entries
    .map(e => `${e.accountType}:${D(e.debit).toString()}/${D(e.credit).toString()}`)
    .sort()
    .join('|')
  // Node global Buffer + crypto available in server runtime.
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const crypto = require('crypto')
  return crypto.createHash('sha256').update(payload).digest('hex')
}
