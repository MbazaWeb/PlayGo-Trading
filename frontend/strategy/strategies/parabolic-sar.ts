import type { Strategy } from '../types';
import { evaluateStrategy } from '../engine';
export const strategy: Strategy = { id: 'parabolic-sar', name: "Parabolic SAR", category: "Trend", evaluate: (candles, config) => evaluateStrategy('parabolic-sar', candles, config) };
export default strategy;
