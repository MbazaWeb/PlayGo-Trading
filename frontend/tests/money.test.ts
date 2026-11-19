// money.test.ts — Pure unit tests for the Decimal-safe monetary core.
// No database access.
import { test, expect, describe } from 'bun:test'
import { Decimal } from 'decimal.js'
import {
  D,
  add,
  sub,
  mul,
  div,
  round,
  toPip,
  ledgerBalances,
  hashJournal,
  fmtMoney,
} from '@/lib/money'

describe('money — D()', () => {
  test('parses strings, numbers, null, undefined, Decimal', () => {
    expect(D('1.5').eq(new Decimal('1.5'))).toBe(true)
    expect(D(2).eq(new Decimal(2))).toBe(true)
    expect(D(null).eq(new Decimal(0))).toBe(true)
    expect(D(undefined).eq(new Decimal(0))).toBe(true)
    expect(D(new Decimal('3.14')).eq(new Decimal('3.14'))).toBe(true)
    expect(D('0.0001').eq(new Decimal('0.0001'))).toBe(true)
  })
})

describe('money — arithmetic', () => {
  test('add / sub / mul / div are correct', () => {
    expect(add('1.5', '2.5').toString()).toBe('4')
    expect(sub('10', '3').toString()).toBe('7')
    expect(mul('2', '3.5').toString()).toBe('7')
    expect(div('10', '4').toString()).toBe('2.5')
    expect(mul('0.1', '0.2').toString()).toBe('0.02') // no float error
  })

  test('div by zero throws', () => {
    expect(() => div('1', '0')).toThrow('Division by zero')
    expect(() => div('1', 0)).toThrow('Division by zero')
    expect(() => div('5', D(0))).toThrow('Division by zero')
  })
})

describe('money — rounding', () => {
  test('round half-up to 2dp', () => {
    expect(round('1.005', 2).toString()).toBe('1.01')
    expect(round('1.234', 2).toString()).toBe('1.23')
    expect(round('1.235', 2).toString()).toBe('1.24')
    expect(round('2.675', 2).toString()).toBe('2.68')
    expect(round('0.005', 2).toString()).toBe('0.01')
    expect(round('0.004', 2).eq(new Decimal(0))).toBe(true) // below half -> 0.00
  })

  test('round default dp is 2', () => {
    expect(round('9.999').toString()).toBe('10')
  })

  test('toPip rounds to pip precision', () => {
    // pipSize '0.0001' has 4 decimal places
    expect(toPip('1.08505', '0.0001').eq(new Decimal('1.0851'))).toBe(true)
    expect(toPip('1.08504', '0.0001').eq(new Decimal('1.085'))).toBe(true)
    // pipSize '0.01' (JPY) has 2 decimal places
    expect(toPip('151.235', '0.01').eq(new Decimal('151.24'))).toBe(true)
    expect(toPip('151.234', '0.01').eq(new Decimal('151.23'))).toBe(true)
  })
})

describe('money — ledgerBalances', () => {
  test('balanced when debit == credit', () => {
    const r = ledgerBalances([
      { debit: '100', credit: '0' },
      { debit: '0', credit: '100' },
    ])
    expect(r.balanced).toBe(true)
    expect(r.debit.eq(new Decimal(100))).toBe(true)
    expect(r.credit.eq(new Decimal(100))).toBe(true)
  })

  test('unbalanced when debit != credit', () => {
    const r = ledgerBalances([
      { debit: '100', credit: '0' },
      { debit: '0', credit: '50' },
    ])
    expect(r.balanced).toBe(false)
    expect(r.debit.eq(new Decimal(100))).toBe(true)
    expect(r.credit.eq(new Decimal(50))).toBe(true)
  })

  test('empty entries balanced (0 == 0)', () => {
    const r = ledgerBalances([])
    expect(r.balanced).toBe(true)
    expect(r.debit.eq(new Decimal(0))).toBe(true)
  })
})

describe('money — hashJournal', () => {
  test('is deterministic: same input -> same hash', () => {
    const entries = [
      { accountType: 'CASH', debit: '100', credit: '0' },
      { accountType: 'CAPITAL', debit: '0', credit: '100' },
    ]
    const h1 = hashJournal('j1', 'OPENING_CAPITAL', entries)
    const h2 = hashJournal('j1', 'OPENING_CAPITAL', entries)
    expect(h1).toBe(h2)
  })

  test('is 64-char lowercase hex', () => {
    const h = hashJournal('j1', 'OPENING_CAPITAL', [
      { accountType: 'CASH', debit: '1', credit: '0' },
      { accountType: 'CAPITAL', debit: '0', credit: '1' },
    ])
    expect(h).toMatch(/^[0-9a-f]{64}$/)
  })

  test('different journalId -> different hash', () => {
    const entries = [
      { accountType: 'CASH', debit: '100', credit: '0' },
      { accountType: 'CAPITAL', debit: '0', credit: '100' },
    ]
    expect(hashJournal('j1', 'OPENING_CAPITAL', entries)).not.toBe(
      hashJournal('j2', 'OPENING_CAPITAL', entries)
    )
  })

  test('different type -> different hash', () => {
    const entries = [
      { accountType: 'CASH', debit: '100', credit: '0' },
      { accountType: 'CAPITAL', debit: '0', credit: '100' },
    ]
    expect(hashJournal('j1', 'OPENING_CAPITAL', entries)).not.toBe(
      hashJournal('j1', 'TRADE', entries)
    )
  })

  test('different entries -> different hash', () => {
    const e1 = [
      { accountType: 'CASH', debit: '100', credit: '0' },
      { accountType: 'CAPITAL', debit: '0', credit: '100' },
    ]
    const e2 = [
      { accountType: 'CASH', debit: '200', credit: '0' },
      { accountType: 'CAPITAL', debit: '0', credit: '200' },
    ]
    expect(hashJournal('j1', 'OPENING_CAPITAL', e1)).not.toBe(
      hashJournal('j1', 'OPENING_CAPITAL', e2)
    )
  })
})

describe('money — fmtMoney', () => {
  test('formats with thousands separator and fixed dp', () => {
    expect(fmtMoney('1234.5')).toBe('1,234.50')
    expect(fmtMoney('1234.567', 2)).toBe('1,234.57')
    expect(fmtMoney('0')).toBe('0.00')
  })
})
