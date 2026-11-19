import type { Strategy } from '../types';
import { evaluateStrategy } from '../engine';
export const strategy: Strategy = { id: 'previous-high-low-breakout', name: "Previous High Low Breakout", category: "Breakout", evaluate: (candles, config) => evaluateStrategy('previous-high-low-breakout', candles, config) };
export default strategy;
