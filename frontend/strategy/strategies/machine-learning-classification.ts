import type { Strategy } from '../types';
import { evaluateStrategy } from '../engine';
export const strategy: Strategy = { id: 'machine-learning-classification', name: "Machine Learning Classification", category: "Quantitative", evaluate: (candles, config) => evaluateStrategy('machine-learning-classification', candles, config) };
export default strategy;
