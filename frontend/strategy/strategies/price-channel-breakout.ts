import type { Strategy } from '../types';
import { evaluateStrategy } from '../engine';
export const strategy: Strategy = { id: 'price-channel-breakout', name: "Price Channel Breakout", category: "Breakout", evaluate: (candles, config) => evaluateStrategy('price-channel-breakout', candles, config) };
export default strategy;
