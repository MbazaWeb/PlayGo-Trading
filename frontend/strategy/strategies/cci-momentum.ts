import type { Strategy } from '../types';
import { evaluateStrategy } from '../engine';
export const strategy: Strategy = { id: 'cci-momentum', name: "CCI Momentum", category: "Momentum", evaluate: (candles, config) => evaluateStrategy('cci-momentum', candles, config) };
export default strategy;
