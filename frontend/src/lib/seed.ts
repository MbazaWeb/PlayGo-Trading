// seed.ts — Idempotent dev seed.
// Seeds instruments, a demo user, a PAPER trading account, opening capital
// journal (USD 10,000), default risk limits, sample strategies, and a system
// health baseline. Safe to call repeatedly.
import { db } from '@/lib/db'
import { ensureInstruments } from '@/lib/market'
import { hashPassword } from '@/lib/auth'
import { postOpeningCapital } from '@/lib/accounting'
import { audit } from '@/lib/audit'

export async function seedIfEmpty() {
  await ensureInstruments()

  let user = await db.user.findUnique({ where: { email: 'trader@playgo.local' } })
  if (!user) {
    user = await db.user.create({
      data: {
        email: 'trader@playgo.local',
        name: 'PlayGo Trader',
        passwordHash: await hashPassword('PlayGo2025!'),
        role: 'ADMIN',
      },
    })
    await audit({ userId: user.id, action: 'USER_SEED', entity: 'User', entityId: user.id })
  }

  let account = await db.tradingAccount.findFirst({ where: { userId: user.id } })
  if (!account) {
    account = await db.tradingAccount.create({
      data: {
        userId: user.id,
        label: 'Primary PAPER Account',
        mode: 'PAPER',
        broker: 'PAPER',
        currency: 'USD',
        liveAuthorized: false,
      },
    })
    // Opening capital journal — idempotent.
    await postOpeningCapital(account.id, '10000.00', user.id)
    // Default risk limits.
    await db.riskLimit.create({
      data: {
        tradingAccountId: account.id,
        version: 1,
        maxPositionSize: '10',
        maxLeverage: '30',
        maxDailyLossPct: '5',
        maxWeeklyLossPct: '10',
        maxDrawdownPct: '20',
        maxAggregateExposure: '50000',
        maxSimultaneousPositions: 10,
        maxSpreadPips: '5',
        maxSlippagePips: '3',
        active: true,
      },
    })
    // Paper broker connection.
    await db.brokerConnection.create({
      data: {
        tradingAccountId: account.id,
        broker: 'PAPER',
        mode: 'PAPER',
        status: 'CONNECTED',
        permissions: 'TRADE',
        lastCheckedAt: new Date(),
      },
    })
  }

  // Sample strategies.
  const stratCount = await db.strategy.count()
  if (stratCount === 0) {
    await db.strategy.create({
      data: {
        name: 'MA Crossover (Fast/Slow)',
        version: 1,
        description: 'Moving-average crossover with SL/TP. Deterministic backtestable baseline strategy.',
        entryRules: JSON.stringify({ fastCrossAboveSlow: 'BUY', fastCrossBelowSlow: 'SELL' }),
        exitRules: JSON.stringify({ stopLossPips: 20, takeProfitPips: 40, oppositeCross: true }),
        positionSizing: JSON.stringify({ fixedSize: 1 }),
        instruments: 'EUR/USD,GBP/USD,USD/JPY,AUD/USD,R_100,R_75',
        timeframes: 'M5,M15,H1',
        maxDrawdownPct: 20,
        status: 'VALIDATED',
      },
    })
    await db.strategy.create({
      data: {
        name: 'Volatility Breakout (R_100)',
        version: 1,
        description: 'Breakout entry on synthetic volatility index. Clearly labeled PAPER research strategy.',
        entryRules: JSON.stringify({ breakoutAbovePriorHigh: 'BUY', breakoutBelowPriorLow: 'SELL' }),
        exitRules: JSON.stringify({ stopLossPips: 30, takeProfitPips: 60 }),
        positionSizing: JSON.stringify({ fixedSize: 0.5 }),
        instruments: 'R_100,R_75',
        timeframes: 'M5,M15',
        maxDrawdownPct: 25,
        status: 'DRAFT',
      },
    })
  }

  // System health baseline.
  const healthCount = await db.systemHealth.count()
  if (healthCount === 0) {
    for (const comp of ['api', 'database', 'paper_engine', 'market_data', 'accounting', 'risk', 'broker']) {
      await db.systemHealth.create({
        data: { component: comp, status: 'OK', message: 'Initialized', checkedAt: new Date() },
      })
    }
  }

  return { user, account }
}
