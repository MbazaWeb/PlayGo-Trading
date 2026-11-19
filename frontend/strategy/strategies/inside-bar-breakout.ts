import type { Strategy } from '../types';
import { evaluateStrategy } from '../engine';
export const strategy: Strategy = { id: 'inside-bar-breakout', name: "Inside Bar Breakout", category: "Price Action", evaluate: (candles, config) => evaluateStrategy('inside-bar-breakout', candles, config) };
export default strategy;
