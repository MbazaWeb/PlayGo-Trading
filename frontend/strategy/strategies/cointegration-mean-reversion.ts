import type { Strategy } from '../types';
import { evaluateStrategy } from '../engine';
export const strategy: Strategy = { id: 'cointegration-mean-reversion', name: "Cointegration Mean Reversion", category: "Quantitative", evaluate: (candles, config) => evaluateStrategy('cointegration-mean-reversion', candles, config) };
export default strategy;
