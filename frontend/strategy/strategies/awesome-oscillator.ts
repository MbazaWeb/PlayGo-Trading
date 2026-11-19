import type { Strategy } from '../types';
import { evaluateStrategy } from '../engine';
export const strategy: Strategy = { id: 'awesome-oscillator', name: "Awesome Oscillator", category: "Momentum", evaluate: (candles, config) => evaluateStrategy('awesome-oscillator', candles, config) };
export default strategy;
