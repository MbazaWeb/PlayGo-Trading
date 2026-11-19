import type { Strategy } from '../types';
import { evaluateStrategy } from '../engine';
export const strategy: Strategy = { id: 'statistical-arbitrage', name: "Statistical Arbitrage", category: "Quantitative", evaluate: (candles, config) => evaluateStrategy('statistical-arbitrage', candles, config) };
export default strategy;
