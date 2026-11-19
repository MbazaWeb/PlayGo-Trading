import type { Strategy } from '../types';
import { evaluateStrategy } from '../engine';
export const strategy: Strategy = { id: 'moving-average-crossover', name: "Moving Average Crossover", category: "Trend", evaluate: (candles, config) => evaluateStrategy('moving-average-crossover', candles, config) };
export default strategy;
