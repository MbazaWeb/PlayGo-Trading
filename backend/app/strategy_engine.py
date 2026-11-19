"""Deterministic, demo-only evaluation of supported closed-candle strategies."""
from datetime import datetime, timezone
import math


DEFAULT_STRATEGY_ID = "ema-crossover"
SUPPORTED_STRATEGY_IDS = frozenset({
    "moving-average-crossover",
    "ema-crossover",
    "triple-moving-average",
    "macd-crossover",
    "moving-average-pullback",
    "rsi-momentum",
    "rate-of-change",
    "momentum-breakout",
    "rsi-oversold-overbought",
    "bollinger-bands-reversion",
    "z-score-reversion",
    "moving-average-reversion",
    "donchian-channel-breakout",
    "support-resistance-breakout",
    "price-channel-breakout",
    "previous-high-low-breakout",
    "consolidation-breakout",
    "atr-breakout",
    "engulfing-candlestick",
    "pin-bar-reversal",
    "inside-bar-breakout",
    "higher-high-higher-low",
    "trend-momentum-hybrid",
    "ensemble-voting",
})

FAST_PERIOD = 9
SLOW_PERIOD = 21
RSI_PERIOD = 14
RSI_OVERSOLD = 30
RSI_OVERBOUGHT = 70
BAND_PERIOD = 20
BAND_STD_DEV = 2
ATR_PERIOD = 14
BREAKOUT_PERIOD = 20


def _hold(reason, bar_time=None):
    return {"signal": "HOLD", "reason": reason, "bar_time": bar_time, "ready": False}


def _sma(values, period):
    result = [None] * len(values)
    for index in range(period - 1, len(values)):
        window = values[index - period + 1:index + 1]
        result[index] = sum(window) / period
    return result


def _ema(values, period):
    result = [None] * len(values)
    if len(values) < period:
        return result
    current = sum(values[:period]) / period
    result[period - 1] = current
    multiplier = 2 / (period + 1)
    for index in range(period, len(values)):
        current = values[index] * multiplier + current * (1 - multiplier)
        result[index] = current
    return result


def _stdev(values, period):
    means = _sma(values, period)
    result = [None] * len(values)
    for index in range(period - 1, len(values)):
        mean = means[index]
        window = values[index - period + 1:index + 1]
        result[index] = math.sqrt(sum((value - mean) ** 2 for value in window) / period)
    return result


def _rsi(values, period):
    result = [None] * len(values)
    for index in range(period, len(values)):
        changes = [
            values[current] - values[current - 1]
            for current in range(index - period + 1, index + 1)
        ]
        gain = sum(max(change, 0) for change in changes)
        loss = sum(max(-change, 0) for change in changes)
        result[index] = 50 if gain == 0 and loss == 0 else (
            100 if loss == 0 else 100 - 100 / (1 + gain / loss)
        )
    return result


def _atr(candles, period):
    ranges = []
    for index, candle in enumerate(candles):
        high, low = candle["high"], candle["low"]
        if index == 0:
            ranges.append(high - low)
        else:
            previous_close = candles[index - 1]["close"]
            ranges.append(max(
                high - low,
                abs(high - previous_close),
                abs(low - previous_close),
            ))
    return _sma(ranges, period)


def _crosses_up(left, right, index):
    return (
        index > 0
        and left[index - 1] is not None
        and right[index - 1] is not None
        and left[index] is not None
        and right[index] is not None
        and left[index - 1] <= right[index - 1]
        and left[index] > right[index]
    )


def _crosses_down(left, right, index):
    return (
        index > 0
        and left[index - 1] is not None
        and right[index - 1] is not None
        and left[index] is not None
        and right[index] is not None
        and left[index - 1] >= right[index - 1]
        and left[index] < right[index]
    )


def _cross(left, right, index):
    if _crosses_up(left, right, index):
        return "BUY"
    if _crosses_down(left, right, index):
        return "SELL"
    return "HOLD"


def _breakout(candles, index):
    past = candles[index - BREAKOUT_PERIOD:index]
    highest = max(item["high"] for item in past)
    lowest = min(item["low"] for item in past)
    close = candles[index]["close"]
    return "BUY" if close > highest else "SELL" if close < lowest else "HOLD"


def evaluate_strategy(strategy_id, raw_candles):
    """Evaluate one supported strategy on completed Deriv candles only."""
    if strategy_id not in SUPPORTED_STRATEGY_IDS:
        return _hold("Research-only strategy; no supported rule-based evaluator")
    if not isinstance(raw_candles, list):
        return _hold("Invalid candle data")

    candles = []
    previous_epoch = 0
    try:
        for raw in raw_candles:
            epoch = int(raw["epoch"])
            candle = {
                name: float(raw[name])
                for name in ("open", "high", "low", "close")
            }
            if (
                epoch <= previous_epoch
                or any(not math.isfinite(value) or value <= 0 for value in candle.values())
                or candle["high"] < max(candle["open"], candle["close"], candle["low"])
                or candle["low"] > min(candle["open"], candle["close"], candle["high"])
            ):
                return _hold("Invalid or unsorted closed candles")
            candles.append({"epoch": epoch, **candle})
            previous_epoch = epoch
    except (KeyError, TypeError, ValueError, OverflowError):
        return _hold("Invalid candle data")

    strategy_period = (
        SLOW_PERIOD * 2 if strategy_id == "triple-moving-average"
        else 34 if strategy_id == "macd-crossover"
        else 0
    )
    if len(candles) < max(
        SLOW_PERIOD,
        BAND_PERIOD,
        BREAKOUT_PERIOD,
        RSI_PERIOD,
        ATR_PERIOD,
        strategy_period,
    ) + 5:
        return _hold("Insufficient closed candles")

    try:
        bar_time = datetime.fromtimestamp(candles[-1]["epoch"], timezone.utc).isoformat()
    except (OverflowError, OSError, ValueError):
        return _hold("Invalid candle timestamp")

    close = [item["close"] for item in candles]
    index = len(close) - 1
    fast = _ema(close, FAST_PERIOD)
    slow = _ema(close, SLOW_PERIOD)
    moving_average = _sma(close, SLOW_PERIOD)
    relative_strength = _rsi(close, RSI_PERIOD)
    average_range = _atr(candles, ATR_PERIOD)
    deviation = _stdev(close, BAND_PERIOD)
    band_midpoint = _sma(close, BAND_PERIOD)
    trend = "BUY" if fast[index] > slow[index] else "SELL"
    signal = "HOLD"

    if strategy_id == "moving-average-crossover":
        signal = _cross(_sma(close, FAST_PERIOD), moving_average, index)
    elif strategy_id == "ema-crossover":
        signal = _cross(fast, slow, index)
    elif strategy_id == "triple-moving-average":
        long_average = _sma(close, SLOW_PERIOD * 2)
        signal = (
            "BUY" if fast[index] > slow[index] and slow[index] > long_average[index]
            else "SELL" if fast[index] < slow[index] and slow[index] < long_average[index]
            else "HOLD"
        )
    elif strategy_id == "macd-crossover":
        fast_macd = _ema(close, 12)
        slow_macd = _ema(close, 26)
        macd = [
            fast_macd[i] - slow_macd[i]
            if fast_macd[i] is not None and slow_macd[i] is not None else None
            for i in range(len(close))
        ]
        valid_macd = [value for value in macd[25:] if value is not None]
        signal_values = _ema(valid_macd, 9)
        line = [None] * 25 + signal_values
        signal = _cross(macd, line, index)
    elif strategy_id == "moving-average-pullback":
        signal = (
            "BUY" if close[index] > slow[index] and candles[index]["low"] <= slow[index]
            else "SELL" if close[index] < slow[index] and candles[index]["high"] >= slow[index]
            else "HOLD"
        )
    elif strategy_id == "rsi-momentum":
        signal = "BUY" if relative_strength[index] > 55 else "SELL" if relative_strength[index] < 45 else "HOLD"
    elif strategy_id == "rate-of-change":
        reference = close[index - FAST_PERIOD]
        signal = "BUY" if close[index] > reference * 1.01 else "SELL" if close[index] < reference * 0.99 else "HOLD"
    elif strategy_id == "momentum-breakout":
        signal = _breakout(candles, index)
        if signal == "BUY" and relative_strength[index] < 55 or signal == "SELL" and relative_strength[index] > 45:
            signal = "HOLD"
    elif strategy_id == "rsi-oversold-overbought":
        value = relative_strength[index]
        signal = "BUY" if value < RSI_OVERSOLD else "SELL" if value > RSI_OVERBOUGHT else "HOLD"
    elif strategy_id in {"bollinger-bands-reversion", "z-score-reversion"}:
        midpoint, std = band_midpoint[index], deviation[index]
        signal = "BUY" if close[index] < midpoint - BAND_STD_DEV * std else "SELL" if close[index] > midpoint + BAND_STD_DEV * std else "HOLD"
    elif strategy_id == "moving-average-reversion":
        signal = "BUY" if close[index] < moving_average[index] - 2 * average_range[index] else "SELL" if close[index] > moving_average[index] + 2 * average_range[index] else "HOLD"
    elif strategy_id in {
        "donchian-channel-breakout",
        "support-resistance-breakout",
        "price-channel-breakout",
        "previous-high-low-breakout",
        "consolidation-breakout",
    }:
        signal = _breakout(candles, index)
    elif strategy_id == "atr-breakout":
        boundary = 1.5 * average_range[index]
        signal = "BUY" if close[index] > close[index - 1] + boundary else "SELL" if close[index] < close[index - 1] - boundary else "HOLD"
    elif strategy_id == "engulfing-candlestick":
        previous, current = candles[index - 1], candles[index]
        signal = (
            "BUY" if previous["close"] < previous["open"] and current["close"] > current["open"]
            and current["open"] <= previous["close"] and current["close"] >= previous["open"]
            else "SELL" if previous["close"] > previous["open"] and current["close"] < current["open"]
            and current["open"] >= previous["close"] and current["close"] <= previous["open"]
            else "HOLD"
        )
    elif strategy_id == "pin-bar-reversal":
        current = candles[index]
        candle_range = current["high"] - current["low"]
        body = abs(current["close"] - current["open"])
        signal = (
            "BUY" if candle_range > 0 and body / candle_range < 0.35
            and min(current["open"], current["close"]) - current["low"] > candle_range * 0.6
            else "SELL" if candle_range > 0 and body / candle_range < 0.35
            and current["high"] - max(current["open"], current["close"]) > candle_range * 0.6
            else "HOLD"
        )
    elif strategy_id == "inside-bar-breakout":
        previous, mother = candles[index - 1], candles[index - 2]
        signal = (
            "BUY" if previous["high"] < mother["high"] and previous["low"] > mother["low"]
            and close[index] > mother["high"]
            else "SELL" if previous["high"] < mother["high"] and previous["low"] > mother["low"]
            and close[index] < mother["low"]
            else "HOLD"
        )
    elif strategy_id == "higher-high-higher-low":
        current, previous = candles[index], candles[index - 1]
        signal = (
            "BUY" if current["high"] > previous["high"] and current["low"] > previous["low"]
            else "SELL" if current["high"] < previous["high"] and current["low"] < previous["low"]
            else "HOLD"
        )
    elif strategy_id == "trend-momentum-hybrid":
        signal = (
            "BUY" if trend == "BUY" and relative_strength[index] > 55
            else "SELL" if trend == "SELL" and relative_strength[index] < 45
            else "HOLD"
        )
    elif strategy_id == "ensemble-voting":
        rsi_vote = "BUY" if relative_strength[index] < 40 else "SELL" if relative_strength[index] > 60 else "HOLD"
        votes = [trend, rsi_vote, _breakout(candles, index)]
        buy_votes, sell_votes = votes.count("BUY"), votes.count("SELL")
        signal = "BUY" if buy_votes >= 2 else "SELL" if sell_votes >= 2 else "HOLD"

    return {
        "signal": signal,
        "reason": (
            f"Rule-based {strategy_id} signal on latest CLOSED candle; not an order"
            if signal != "HOLD" else "Conditions not met"
        ),
        "bar_time": bar_time,
        "ready": True,
    }
