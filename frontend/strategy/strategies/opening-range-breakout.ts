import type { Strategy } from '../types';
import { evaluateStrategy } from '../engine';
export const strategy: Strategy = { id: 'opening-range-breakout', name: "Opening Range Breakout", category: "Breakout", evaluate: (candles, config) => evaluateStrategy('opening-range-breakout', candles, config) };
export default strategy;
