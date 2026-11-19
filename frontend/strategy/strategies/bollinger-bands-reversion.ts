import type { Strategy } from '../types';
import { evaluateStrategy } from '../engine';
export const strategy: Strategy = { id: 'bollinger-bands-reversion', name: "Bollinger Bands Reversion", category: "Mean Reversion", evaluate: (candles, config) => evaluateStrategy('bollinger-bands-reversion', candles, config) };
export default strategy;
