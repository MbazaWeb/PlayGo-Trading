import type { Strategy } from '../types';
import { evaluateStrategy } from '../engine';
export const strategy: Strategy = { id: 'consolidation-breakout', name: "Consolidation Breakout", category: "Breakout", evaluate: (candles, config) => evaluateStrategy('consolidation-breakout', candles, config) };
export default strategy;
