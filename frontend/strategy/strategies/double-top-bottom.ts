import type { Strategy } from '../types';
import { evaluateStrategy } from '../engine';
export const strategy: Strategy = { id: 'double-top-bottom', name: "Double Top Bottom", category: "Price Action", evaluate: (candles, config) => evaluateStrategy('double-top-bottom', candles, config) };
export default strategy;
