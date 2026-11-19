import type { Strategy } from '../types';
import { evaluateStrategy } from '../engine';
export const strategy: Strategy = { id: 'higher-high-higher-low', name: "Higher High Higher Low", category: "Price Action", evaluate: (candles, config) => evaluateStrategy('higher-high-higher-low', candles, config) };
export default strategy;
