import type { Strategy } from '../types';
import { evaluateStrategy } from '../engine';
export const strategy: Strategy = { id: 'moving-average-reversion', name: "Moving Average Reversion", category: "Mean Reversion", evaluate: (candles, config) => evaluateStrategy('moving-average-reversion', candles, config) };
export default strategy;
