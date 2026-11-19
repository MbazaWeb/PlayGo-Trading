import type { Strategy } from '../types';
import { evaluateStrategy } from '../engine';
export const strategy: Strategy = { id: 'walk-forward-adaptive-strategy', name: "Walk Forward Adaptive Strategy", category: "Quantitative", evaluate: (candles, config) => evaluateStrategy('walk-forward-adaptive-strategy', candles, config) };
export default strategy;
