# Paper breakout research

`GET /api/research/breakout` runs an authenticated, read-only research request
against Deriv public candle history. It does not initialize, write, or settle
the paper account, and it never sends a trading command.

Keep research runs separate from Deriv demo execution. The dashboard's demo bot uses an EMA 9/21 crossover strategy, while this endpoint simulates a breakout strategy. Dashboard P&L comes from Deriv contracts. See the [dashboard overview](../../README.md) for those flows.

The endpoint accepts `EURUSD` or `GBPUSD`, a supported candle interval, and
bounded strategy and cost assumptions. The public WebSocket connection
requires no App ID or account token.

## Simulation method

- A breakout is confirmed only after a candle closes beyond the previous
  lookback window's high or low.
- Entry is simulated at the next candle's open.
- Stop distance is based on the lookback average true range; the target uses
  the configured reward/risk multiple.
- The risk budget and a USD notional cap bound simulated position size.
- If a candle crosses both stop and target, the stop is applied first.
- The user-provided spread and per-side slippage estimates are deducted from
  simulated P&L. The spread assumption is also compared with the configured
  maximum-spread gate.

Deriv's public candle history does not expose order-book depth or bid/ask
liquidity. The cost gate is therefore an assumption check, not a liquidity
measurement. Results include closed-trade drawdown only and exclude intrabar
unrealized drawdown. Historical simulations do not predict future results.

## Inspiration reviewed

The feature uses original code and only general research concepts; no bot
source, executable, model, or third-party skill package is imported.

- [Crypto AI Trading Bot](https://github.com/SamDesantos/Crypto-Ai-Trading-Bot)
- [Intraday Breakout Trading Bot](https://github.com/jahanzaib-codes/intelligent-intraday-breakout-trading-bot)
- [IBKR Telegram Trading Bot](https://github.com/jahanzaib-codes/ibkr-telegram-trading-bot)
- [Liquidity Sniping Bot](https://github.com/RangerByChance/Liquidity-Sniping-Bot-PC-resp-Windows)
- [Claude Trading Skills](https://github.com/tradermonty/claude-trading-skills)

Broker execution, sniping, model-based win probabilities, and Telegram order
commands are intentionally not implemented.
