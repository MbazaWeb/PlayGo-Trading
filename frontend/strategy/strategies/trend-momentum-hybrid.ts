import type { Strategy } from '../types';
import { evaluateStrategy } from '../engine';
export const strategy: Strategy = { id: 'trend-momentum-hybrid', name: "Trend Momentum Hybrid", category: "Quantitative", evaluate: (candles, config) => evaluateStrategy('trend-momentum-hybrid', candles, config) };
export default strategy;
