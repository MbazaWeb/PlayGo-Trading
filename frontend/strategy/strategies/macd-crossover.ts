import type { Strategy } from '../types';
import { evaluateStrategy } from '../engine';
export const strategy: Strategy = { id: 'macd-crossover', name: "MACD Crossover", category: "Trend", evaluate: (candles, config) => evaluateStrategy('macd-crossover', candles, config) };
export default strategy;
