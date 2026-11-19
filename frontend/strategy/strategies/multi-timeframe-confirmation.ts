import type { Strategy } from '../types';
import { evaluateStrategy } from '../engine';
export const strategy: Strategy = { id: 'multi-timeframe-confirmation', name: "Multi Timeframe Confirmation", category: "Quantitative", evaluate: (candles, config) => evaluateStrategy('multi-timeframe-confirmation', candles, config) };
export default strategy;
