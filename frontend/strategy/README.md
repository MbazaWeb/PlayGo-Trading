# PlayGo strategy package (50 catalog entries)

## PlayGo integration
The Agents page uses this registry for automatic strategy selection. On each new, closed Deriv five-minute candle, the backend evaluates trend, range extremes, breakouts, and volatility, then chooses a supported rule or stands aside. The strategy choice and reason are reported with the latest decision.

Users may provide a constrained JSON filter with `allow_signals`, `min_rsi`, `max_rsi`, and `max_atr_percent`. These rules can only veto an automatic signal; they cannot choose a strategy, force a trade, or execute code. Filters are validated and saved when the user explicitly starts the demo bot. No new npm packages are required.

To display the interactive configurator, import:

```tsx
import { StrategyConfigurator } from '../../../strategy';
// Render <StrategyConfigurator candles={closedCandles} /> in a client component.
```

The standalone configurator below remains a research preview. Its JSON export is not the bot configuration and it does not place orders.

## Coverage and limitations
All 50 strategies have named TypeScript modules and registry entries. **Only the 24 IDs exported as `SUPPORTED_STRATEGY_IDS` have preliminary rule-based signals** in `engine.ts`; the other 26 remain research-only. The automatic selector currently chooses among four of those 24 evaluators: breakout, trend/momentum, RSI reversal, and Bollinger reversion. It stands aside for unclear regimes or unusual volatility. This heuristic is not a profitability guarantee and does not enable LIVE trading.

The MACD, RSI, breakout and other rules require independent tests, historical data validation, spread/slippage modeling and walk-forward evaluation before any deployment. Candles must be closed, timestamp-sorted, and unique. This package does not place orders and cannot enable LIVE trading.

## Example
```ts
import {getStrategy,DEFAULT_CONFIG} from './strategy';
const result=getStrategy('ema-crossover')!.evaluate(closedCandles,DEFAULT_CONFIG);
console.log(result); // BUY, SELL or HOLD, no order placement
```

## Next steps
Add configurable strategy parameters and extend historical validation, specialist models for remaining entries, and safe paper backtesting. Do not treat catalog coverage as trading validation.
