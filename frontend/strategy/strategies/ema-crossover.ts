import type { Strategy } from '../types';
import { evaluateStrategy } from '../engine';
export const strategy: Strategy = { id: 'ema-crossover', name: "EMA Crossover", category: "Trend", evaluate: (candles, config) => evaluateStrategy('ema-crossover', candles, config) };
export default strategy;
