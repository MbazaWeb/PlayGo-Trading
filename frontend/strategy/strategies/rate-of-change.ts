import type { Strategy } from '../types';
import { evaluateStrategy } from '../engine';
export const strategy: Strategy = { id: 'rate-of-change', name: "Rate of Change", category: "Momentum", evaluate: (candles, config) => evaluateStrategy('rate-of-change', candles, config) };
export default strategy;
