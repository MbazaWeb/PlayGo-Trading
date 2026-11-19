import type { Strategy } from '../types';
import { evaluateStrategy } from '../engine';
export const strategy: Strategy = { id: 'pin-bar-reversal', name: "Pin Bar Reversal", category: "Price Action", evaluate: (candles, config) => evaluateStrategy('pin-bar-reversal', candles, config) };
export default strategy;
