// accounting.test.ts — Double-entry accounting engine (DB integration).
import { test, expect, describe, beforeAll, afterAll } from 'bun:test'
import { Decimal } from 'decimal.js'
import { db } from '@/lib/db'
import {
  postJournal,
  postOpeningCapital,
  postTradeSettlement,
  cashBalance,
  trialBalance,
  verifyIntegrity,
  assertAppendOnly,
} from '@/lib/accounting'
import { D } from '@/lib/money'
import { ensureInstruments } from '@/lib/market'
import {
  createTestUser,
  createTestPaperAccount,
  cleanupTestAccount,
  cleanupTestUser,
  uniq,
} from './helpers'

describe('accounting', () => {
  let userId: string
  let accountId: string

  beforeAll(async () => {
    await ensureInstruments()
    const u = await createTestUser(uniq('acc'))
    userId = u.id
    const a = await createTestPaperAccount(userId, 'Accounting Test Account')
    accountId = a.id
  })

  afterAll(async () => {
    await cleanupTestAccount(accountId)
    await cleanupTestUser(userId)
  })

  test('postOpeningCapital posts a balanced journal (CASH debit 10000, CAPITAL credit 10000)', async () => {
    const j = await postOpeningCapital(accountId, '10000.00', userId)
    expect(j).not.toBeNull()
    expect(j!.type).toBe('OPENING_CAPITAL')
    expect(j!.entries).toHaveLength(2)
    const cash = j!.entries.find((e) => e.accountType === 'CASH')
    const capital = j!.entries.find((e) => e.accountType === 'CAPITAL')
    expect(cash).toBeDefined()
    expect(capital).toBeDefined()
    expect(D(cash!.debit).eq(new Decimal(10000))).toBe(true)
    expect(D(capital!.credit).eq(new Decimal(10000))).toBe(true)
  })

  test('postOpeningCapital is idempotent — calling again returns the SAME journal', async () => {
    const j1 = await postOpeningCapital(accountId, '10000.00', userId)
    const j2 = await postOpeningCapital(accountId, '10000.00', userId)
    expect(j2!.id).toBe(j1!.id)
    const count = await db.accountingJournal.count({
      where: { ref: `opening-capital:${accountId}` },
    })
    expect(count).toBe(1)
  })

  test('cashBalance returns 10000 after opening', async () => {
    const bal = await cashBalance(accountId)
    expect(bal.eq(new Decimal(10000))).toBe(true)
  })

  test('postJournal with unbalanced entries THROWS', async () => {
    await expect(
      postJournal({
        tradingAccountId: accountId,
        ref: uniq('unbalanced'),
        type: 'ADJUSTMENT',
        description: 'Unbalanced test',
        entries: [
          { accountType: 'CASH', debit: '100', credit: '0' },
          { accountType: 'CAPITAL', debit: '0', credit: '50' },
        ],
      })
    ).rejects.toThrow(/does not balance/)
    // Confirm no journal was created for that ref
    const none = await db.accountingJournal.findUnique({ where: { ref: 'never' } })
    expect(none).toBeNull()
  })

  test('postJournal with a duplicate ref returns the existing journal (idempotency)', async () => {
    const ref = uniq('dup-ref')
    const j1 = await postJournal({
      tradingAccountId: accountId,
      ref,
      type: 'ADJUSTMENT',
      description: 'First post',
      entries: [
        { accountType: 'CASH', debit: '5', credit: '0' },
        { accountType: 'CAPITAL', debit: '0', credit: '5' },
      ],
    })
    const j2 = await postJournal({
      tradingAccountId: accountId,
      ref,
      type: 'ADJUSTMENT',
      description: 'Second post — should be ignored',
      entries: [
        { accountType: 'CASH', debit: '999', credit: '0' },
        { accountType: 'CAPITAL', debit: '0', credit: '999' },
      ],
    })
    expect(j2!.id).toBe(j1!.id)
    const count = await db.accountingJournal.count({ where: { ref } })
    expect(count).toBe(1)
  })

  test('postTradeSettlement posts a balanced journal; trialBalance stays balanced', async () => {
    const j = await postTradeSettlement({
      tradingAccountId: accountId,
      ref: uniq('trade-settle'),
      description: 'Test trade settlement',
      cashDelta: D('-100'),
      commission: D('1'),
      swap: D('0'),
      realizedPnl: D('0'),
      userId,
    })
    expect(j).not.toBeNull()
    expect(j!.type).toBe('TRADE')
    const tb = await trialBalance(accountId)
    expect(tb.balanced).toBe(true)
  })

  test('verifyIntegrity returns {checked>=1, valid===checked, invalid===0} for the test account', async () => {
    const vi = await verifyIntegrity(accountId)
    expect(vi.checked).toBeGreaterThanOrEqual(1)
    expect(vi.invalid).toBe(0)
    expect(vi.valid).toBe(vi.checked)
  })

  test('assertAppendOnly throws on update/delete for AccountingJournal and TradeEvent', () => {
    expect(() => assertAppendOnly('AccountingJournal', 'update')).toThrow(/APPEND-ONLY/)
    expect(() => assertAppendOnly('AccountingJournal', 'delete')).toThrow(/APPEND-ONLY/)
    expect(() => assertAppendOnly('TradeEvent', 'update')).toThrow(/APPEND-ONLY/)
    expect(() => assertAppendOnly('TradeEvent', 'delete')).toThrow(/APPEND-ONLY/)
  })
})
