export type Candle = { ts: string; open: number; high: number; low: number; close: number; volume?: number };
export type Signal = 'BUY' | 'SELL' | 'HOLD';
export type StrategyConfig = { timeframe: string; fastPeriod: number; slowPeriod: number; rsiPeriod: number; rsiOversold: number; rsiOverbought: number; bandPeriod: number; bandStdDev: number; atrPeriod: number; atrMultiplier: number; breakoutPeriod: number; stopLossMethod: 'atr'|'structure'|'fixed'; riskPct: number; stopLossPct: number; rewardRisk: number; paperOnly: true };
export type StrategyResult = { signal: Signal; reason: string; barTime: string | null; ready: boolean };
export type Strategy = { id: string; name: string; category: string; evaluate: (candles: Candle[], config: StrategyConfig) => StrategyResult };
