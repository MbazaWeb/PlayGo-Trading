import type { Strategy } from '../types';
import { evaluateStrategy } from '../engine';
export const strategy: Strategy = { id: 'stochastic-crossover', name: "Stochastic Crossover", category: "Momentum", evaluate: (candles, config) => evaluateStrategy('stochastic-crossover', candles, config) };
export default strategy;
