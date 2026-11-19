import type { Strategy } from '../types';
import { evaluateStrategy } from '../engine';
export const strategy: Strategy = { id: 'rsi-oversold-overbought', name: "RSI Oversold Overbought", category: "Mean Reversion", evaluate: (candles, config) => evaluateStrategy('rsi-oversold-overbought', candles, config) };
export default strategy;
