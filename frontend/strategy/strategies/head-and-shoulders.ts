import type { Strategy } from '../types';
import { evaluateStrategy } from '../engine';
export const strategy: Strategy = { id: 'head-and-shoulders', name: "Head and Shoulders", category: "Price Action", evaluate: (candles, config) => evaluateStrategy('head-and-shoulders', candles, config) };
export default strategy;
