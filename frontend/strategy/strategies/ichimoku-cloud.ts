import type { Strategy } from '../types';
import { evaluateStrategy } from '../engine';
export const strategy: Strategy = { id: 'ichimoku-cloud', name: "Ichimoku Cloud", category: "Trend", evaluate: (candles, config) => evaluateStrategy('ichimoku-cloud', candles, config) };
export default strategy;
