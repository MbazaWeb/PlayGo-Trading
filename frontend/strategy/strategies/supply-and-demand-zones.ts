import type { Strategy } from '../types';
import { evaluateStrategy } from '../engine';
export const strategy: Strategy = { id: 'supply-and-demand-zones', name: "Supply and Demand Zones", category: "Price Action", evaluate: (candles, config) => evaluateStrategy('supply-and-demand-zones', candles, config) };
export default strategy;
