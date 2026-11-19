import type { Strategy } from '../types';
import { evaluateStrategy } from '../engine';
export const strategy: Strategy = { id: 'adx-trend-following', name: "ADX Trend Following", category: "Trend", evaluate: (candles, config) => evaluateStrategy('adx-trend-following', candles, config) };
export default strategy;
