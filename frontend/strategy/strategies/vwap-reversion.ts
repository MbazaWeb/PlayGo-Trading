import type { Strategy } from '../types';
import { evaluateStrategy } from '../engine';
export const strategy: Strategy = { id: 'vwap-reversion', name: "VWAP Reversion", category: "Mean Reversion", evaluate: (candles, config) => evaluateStrategy('vwap-reversion', candles, config) };
export default strategy;
