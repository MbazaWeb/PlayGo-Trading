import type { Strategy } from '../types';
import { evaluateStrategy } from '../engine';
export const strategy: Strategy = { id: 'donchian-channel-breakout', name: "Donchian Channel Breakout", category: "Trend", evaluate: (candles, config) => evaluateStrategy('donchian-channel-breakout', candles, config) };
export default strategy;
