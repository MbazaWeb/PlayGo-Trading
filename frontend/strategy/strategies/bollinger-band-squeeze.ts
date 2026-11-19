import type { Strategy } from '../types';
import { evaluateStrategy } from '../engine';
export const strategy: Strategy = { id: 'bollinger-band-squeeze', name: "Bollinger Band Squeeze", category: "Breakout", evaluate: (candles, config) => evaluateStrategy('bollinger-band-squeeze', candles, config) };
export default strategy;
