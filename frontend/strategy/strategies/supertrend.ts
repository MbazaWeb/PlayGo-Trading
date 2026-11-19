import type { Strategy } from '../types';
import { evaluateStrategy } from '../engine';
export const strategy: Strategy = { id: 'supertrend', name: "Supertrend", category: "Trend", evaluate: (candles, config) => evaluateStrategy('supertrend', candles, config) };
export default strategy;
