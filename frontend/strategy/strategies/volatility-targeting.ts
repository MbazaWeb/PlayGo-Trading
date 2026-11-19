import type { Strategy } from '../types';
import { evaluateStrategy } from '../engine';
export const strategy: Strategy = { id: 'volatility-targeting', name: "Volatility Targeting", category: "Quantitative", evaluate: (candles, config) => evaluateStrategy('volatility-targeting', candles, config) };
export default strategy;
