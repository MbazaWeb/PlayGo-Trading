# PlayGo strategy package (50 catalog entries)

## PlayGo integration
The Agents page uses this registry to select a strategy for the demo bot. Strategy selection is sent when the bot starts, and the backend evaluates the selected rule on the latest completed Deriv five-minute candles. No new npm packages are required.

To display the interactive configurator, import:

```tsx
import { StrategyConfigurator } from '../../../strategy';
// Render <StrategyConfigurator candles={closedCandles} /> in a client component.
```

The standalone configurator below remains a research preview. Its JSON export is not the bot configuration and it does not place orders.

## Coverage and limitations
All 50 strategies have named TypeScript modules and registry entries. **Only the 24 IDs exported as `SUPPORTED_STRATEGY_IDS` have preliminary rule-based signals** in `engine.ts` and may be selected for the demo bot; the other 26 remain research-only and are disabled. The backend has a matching deterministic evaluator. Signals use closed candles and never bypass the demo account, stake cap, daily budget, or purchase safeguards. These rules are not validated as profitable and do not enable LIVE trading.

The MACD, RSI, breakout and other rules require independent tests, historical data validation, spread/slippage modeling and walk-forward evaluation before any deployment. Candles must be closed, timestamp-sorted, and unique. This package does not place orders and cannot enable LIVE trading.

## Example
```ts
import {getStrategy,DEFAULT_CONFIG} from './strategy';
const result=getStrategy('ema-crossover')!.evaluate(closedCandles,DEFAULT_CONFIG);
console.log(result); // BUY, SELL or HOLD, no order placement
```

## Next steps
Add configurable strategy parameters and extend historical validation, specialist models for remaining entries, and safe paper backtesting. Do not treat catalog coverage as trading validation.
