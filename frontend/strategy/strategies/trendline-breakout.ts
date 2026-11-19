import type { Strategy } from '../types';
import { evaluateStrategy } from '../engine';
export const strategy: Strategy = { id: 'trendline-breakout', name: "Trendline Breakout", category: "Price Action", evaluate: (candles, config) => evaluateStrategy('trendline-breakout', candles, config) };
export default strategy;
