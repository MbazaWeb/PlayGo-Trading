import type { Strategy } from '../types';
import { evaluateStrategy } from '../engine';
export const strategy: Strategy = { id: 'rsi-momentum', name: "RSI Momentum", category: "Momentum", evaluate: (candles, config) => evaluateStrategy('rsi-momentum', candles, config) };
export default strategy;
