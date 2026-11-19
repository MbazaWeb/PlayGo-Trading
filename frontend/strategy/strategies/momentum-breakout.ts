import type { Strategy } from '../types';
import { evaluateStrategy } from '../engine';
export const strategy: Strategy = { id: 'momentum-breakout', name: "Momentum Breakout", category: "Momentum", evaluate: (candles, config) => evaluateStrategy('momentum-breakout', candles, config) };
export default strategy;
