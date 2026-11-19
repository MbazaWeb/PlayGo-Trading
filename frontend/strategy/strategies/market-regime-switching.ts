import type { Strategy } from '../types';
import { evaluateStrategy } from '../engine';
export const strategy: Strategy = { id: 'market-regime-switching', name: "Market Regime Switching", category: "Quantitative", evaluate: (candles, config) => evaluateStrategy('market-regime-switching', candles, config) };
export default strategy;
