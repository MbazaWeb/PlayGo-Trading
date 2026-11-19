import type { Strategy } from '../types';
import { evaluateStrategy } from '../engine';
export const strategy: Strategy = { id: 'ensemble-voting', name: "Ensemble Voting", category: "Quantitative", evaluate: (candles, config) => evaluateStrategy('ensemble-voting', candles, config) };
export default strategy;
