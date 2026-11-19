import type { Strategy } from '../types';
import { evaluateStrategy } from '../engine';
export const strategy: Strategy = { id: 'moving-average-pullback', name: "Moving Average Pullback", category: "Trend", evaluate: (candles, config) => evaluateStrategy('moving-average-pullback', candles, config) };
export default strategy;
