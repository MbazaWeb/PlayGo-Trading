import type { Strategy } from '../types';
import { evaluateStrategy } from '../engine';
export const strategy: Strategy = { id: 'triple-moving-average', name: "Triple Moving Average", category: "Trend", evaluate: (candles, config) => evaluateStrategy('triple-moving-average', candles, config) };
export default strategy;
