import type { Strategy } from '../types';
import { evaluateStrategy } from '../engine';
export const strategy: Strategy = { id: 'pairs-trading', name: "Pairs Trading", category: "Quantitative", evaluate: (candles, config) => evaluateStrategy('pairs-trading', candles, config) };
export default strategy;
