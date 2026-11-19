import type { Strategy } from '../types';
import { evaluateStrategy } from '../engine';
export const strategy: Strategy = { id: 'stochastic-reversal', name: "Stochastic Reversal", category: "Mean Reversion", evaluate: (candles, config) => evaluateStrategy('stochastic-reversal', candles, config) };
export default strategy;
