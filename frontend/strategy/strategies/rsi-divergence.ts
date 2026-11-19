import type { Strategy } from '../types';
import { evaluateStrategy } from '../engine';
export const strategy: Strategy = { id: 'rsi-divergence', name: "RSI Divergence", category: "Momentum", evaluate: (candles, config) => evaluateStrategy('rsi-divergence', candles, config) };
export default strategy;
