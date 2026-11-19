import type { Strategy } from '../types';
import { evaluateStrategy } from '../engine';
export const strategy: Strategy = { id: 'atr-breakout', name: "ATR Breakout", category: "Breakout", evaluate: (candles, config) => evaluateStrategy('atr-breakout', candles, config) };
export default strategy;
