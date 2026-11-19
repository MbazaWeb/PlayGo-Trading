# Strategy Validation

## Strategy model

A `Strategy` record stores: name, version, description, entry/exit rules (JSON), position sizing (JSON), instruments, timeframes, max drawdown %, and an approval status (`DRAFT` → `VALIDATED` → `APPROVED` → `RETIRED`).

## Backtest engine

`src/lib/backtest.ts` implements a deterministic moving-average-crossover backtest over historical candles:

- **Deterministic replay:** the candle generator (`src/lib/market.ts`) uses a seeded mulberry32 PRNG keyed on the symbol, so the same range/timeframe always yields the same candles. Backtests are reproducible.
- **No look-ahead bias:** entries use only closed candles up to `t-1`; the crossover signal at index `i` uses `fast[i-1]` vs `slow[i-1]` and `fast[i]` vs `slow[i]`.
- **Realistic costs:** commission (0.7 basis points of notional) applied on entry and exit.
- **SL/TP simulation:** intrabar high/low checked against SL/TP levels.

## Metrics computed

| Metric | Formula |
|---|---|
| Net return | final cash − initial capital |
| Net return % | netReturn / initialCapital × 100 |
| Max drawdown | peak-to-trough equity decline |
| Sharpe | mean(per-bar return) / stdev × √252 |
| Sortino | mean / downside-stdev × √252 |
| Calmar | netReturn / maxDrawdown |
| Win rate | wins / trades × 100 |
| Profit factor | Σ profits / Σ losses |
| Expectancy | netReturn / trades |
| Avg gain / loss | gross profit / wins ; gross loss / losses |
| Exposure | (trades × 2) / candle count |
| Turnover | Σ |size × price| over entries |
| Transaction costs | Σ commission |

## Bias & overfitting detection

The engine emits warnings when:
- Trade count < 10 (statistically insignificant)
- Profit factor > 3 with positive return (possible overfitting)
- Max drawdown > 50% (unviable)

**Out-of-sample / walk-forward:** the current engine backtests on a contiguous range. True walk-forward validation (train on window N, test on N+1, roll forward) is a documented production refinement. Do not claim a strategy has an edge without out-of-sample evidence.

## Verified backtest (2026-11-18)

MA Crossover (Fast/Slow) on EUR/USD, M15, 30 days, fast=10, slow=30, SL=20 pips, TP=40 pips, size=1:
- 30 trades
- Win rate 43.33%
- Profit factor 1.625
- Sharpe 0.373
- Sortino 0.278
- Calmar 1.036
- Net return $0.02 (size=1 maps to 1 unit; contract-size multiplier is a known calibration item)

## Strategy approval gate

A strategy moves to `APPROVED` only via `POST /api/strategies/[id]/approve` (audited). Approval does **not** authorize live deployment — that requires the full Phase C gate.

## Do not claim an edge without supporting out-of-sample evidence

Per directive §A7: no strategy is claimed to have an edge based on in-sample backtests alone. The seeded MA Crossover strategy is a baseline research artifact, not a validated edge.
