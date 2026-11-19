import type { Strategy } from '../types';
import { evaluateStrategy } from '../engine';
export const strategy: Strategy = { id: 'engulfing-candlestick', name: "Engulfing Candlestick", category: "Price Action", evaluate: (candles, config) => evaluateStrategy('engulfing-candlestick', candles, config) };
export default strategy;
