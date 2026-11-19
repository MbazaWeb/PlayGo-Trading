import type { Strategy } from '../types';
import { evaluateStrategy } from '../engine';
export const strategy: Strategy = { id: 'support-resistance-breakout', name: "Support Resistance Breakout", category: "Breakout", evaluate: (candles, config) => evaluateStrategy('support-resistance-breakout', candles, config) };
export default strategy;
