import type { Strategy } from '../types';
import { evaluateStrategy } from '../engine';
export const strategy: Strategy = { id: 'keltner-channel-reversion', name: "Keltner Channel Reversion", category: "Mean Reversion", evaluate: (candles, config) => evaluateStrategy('keltner-channel-reversion', candles, config) };
export default strategy;
