import type { Strategy } from '../types';
import { evaluateStrategy } from '../engine';
export const strategy: Strategy = { id: 'z-score-reversion', name: "Z-Score Reversion", category: "Mean Reversion", evaluate: (candles, config) => evaluateStrategy('z-score-reversion', candles, config) };
export default strategy;
