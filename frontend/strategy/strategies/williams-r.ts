import type { Strategy } from '../types';
import { evaluateStrategy } from '../engine';
export const strategy: Strategy = { id: 'williams-r', name: "Williams %R", category: "Momentum", evaluate: (candles, config) => evaluateStrategy('williams-r', candles, config) };
export default strategy;
