"""Offline breakout research over validated public-market candles.

This module never submits orders or writes account state. Results are
illustrative and depend on the supplied data and cost assumptions.
"""
from decimal import Decimal, InvalidOperation, ROUND_FLOOR

SUPPORTED_PAIRS = {"EURUSD", "GBPUSD"}
PIP_SIZE = Decimal("0.0001")
MAX_CANDLES = 1000
MAX_UNITS = 100_000
MAX_NOTIONAL_USD = Decimal("5000")


class BacktestInputError(ValueError):
    pass


def _decimal(value, name):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise BacktestInputError(f"Invalid {name}") from exc
    if not result.is_finite():
        raise BacktestInputError(f"Invalid {name}")
    return result


def _validate_candles(candles):
    if not isinstance(candles, list) or not 1 <= len(candles) <= MAX_CANDLES:
        raise BacktestInputError("Candle count must be between 1 and 1000")

    parsed = []
    previous_epoch = 0
    for candle in candles:
        if not isinstance(candle, dict):
            raise BacktestInputError("Invalid candle")
        try:
            epoch = int(candle["epoch"])
        except (KeyError, TypeError, ValueError) as exc:
            raise BacktestInputError("Invalid candle timestamp") from exc
        if epoch <= previous_epoch:
            raise BacktestInputError("Candle timestamps must be strictly increasing")
        previous_epoch = epoch

        values = {
            key: _decimal(candle.get(key), key)
            for key in ("open", "high", "low", "close")
        }
        open_price = values["open"]
        high = values["high"]
        low = values["low"]
        close = values["close"]
        if (
            min(open_price, high, low, close) <= 0
            or high < max(open_price, close, low)
            or low > min(open_price, close, high)
        ):
            raise BacktestInputError("Candle OHLC values are inconsistent")
        parsed.append({"epoch": epoch, **values})
    return parsed


def _true_range(candles, start, end):
    ranges = []
    for index in range(start, end + 1):
        candle = candles[index]
        previous_close = candles[index - 1]["close"]
        ranges.append(max(
            candle["high"] - candle["low"],
            abs(candle["high"] - previous_close),
            abs(candle["low"] - previous_close),
        ))
    return sum(ranges, Decimal("0")) / Decimal(len(ranges))


def _floor_units(value):
    return int(value.to_integral_value(rounding=ROUND_FLOOR))


def backtest_breakout(
    candles,
    *,
    pair,
    lookback=20,
    starting_balance="10000",
    risk_percent="0.5",
    stop_atr_multiple="1.5",
    reward_risk="2",
    estimated_spread_pips="0.5",
    max_spread_pips="1.5",
    slippage_pips="0.1",
):
    """Run a single-position, close-confirmed breakout simulation.

    A signal is evaluated on a closed candle and entered at the next candle's
    open. If a stop and target are both crossed in one bar, the stop is used.
    """
    if pair not in SUPPORTED_PAIRS:
        raise BacktestInputError("Unsupported currency pair")
    if type(lookback) is not int or not 5 <= lookback <= 100:
        raise BacktestInputError("Lookback must be between 5 and 100 candles")

    data = _validate_candles(candles)
    if len(data) < lookback + 2:
        raise BacktestInputError("Not enough candles for the selected lookback")

    starting = _decimal(starting_balance, "starting balance")
    balance = starting
    risk = _decimal(risk_percent, "risk percent")
    stop_multiple = _decimal(stop_atr_multiple, "stop ATR multiple")
    reward_multiple = _decimal(reward_risk, "reward/risk multiple")
    spread = _decimal(estimated_spread_pips, "estimated spread")
    max_spread = _decimal(max_spread_pips, "maximum spread")
    slippage = _decimal(slippage_pips, "slippage")

    if not Decimal("1") <= balance <= Decimal("1000000000"):
        raise BacktestInputError("Starting balance must be between 1 and 1000000000")
    if not Decimal("0.1") <= risk <= Decimal("1"):
        raise BacktestInputError("Risk percent must be between 0.1 and 1")
    if not Decimal("0.5") <= stop_multiple <= Decimal("5"):
        raise BacktestInputError("Stop ATR multiple must be between 0.5 and 5")
    if not Decimal("0.5") <= reward_multiple <= Decimal("4"):
        raise BacktestInputError("Reward/risk multiple must be between 0.5 and 4")
    if not Decimal("0") <= spread <= Decimal("10"):
        raise BacktestInputError("Estimated spread must be between 0 and 10 pips")
    if not Decimal("0") <= max_spread <= Decimal("10"):
        raise BacktestInputError("Maximum spread must be between 0 and 10 pips")
    if not Decimal("0") <= slippage <= Decimal("5"):
        raise BacktestInputError("Slippage must be between 0 and 5 pips")

    liquidity_filter_passed = spread <= max_spread
    cost_per_unit = (spread + Decimal("2") * slippage) * PIP_SIZE
    trades = []
    peak_balance = balance
    max_drawdown = Decimal("0")
    max_drawdown_peak = balance
    gross_total = Decimal("0")
    costs_total = Decimal("0")
    winners = 0

    index = lookback + 1
    while liquidity_filter_passed and index < len(data):
        signal_index = index - 1
        prior = data[signal_index - lookback:signal_index]
        signal_close = data[signal_index]["close"]
        prior_high = max(candle["high"] for candle in prior)
        prior_low = min(candle["low"] for candle in prior)
        if signal_close > prior_high:
            side = "BUY"
        elif signal_close < prior_low:
            side = "SELL"
        else:
            index += 1
            continue

        entry_candle = data[index]
        entry = entry_candle["open"]
        atr = _true_range(data, signal_index - lookback + 1, signal_index)
        stop_distance = atr * stop_multiple
        if entry <= 0 or stop_distance <= 0:
            index += 1
            continue

        risk_budget = balance * risk / Decimal("100")
        risk_per_unit = stop_distance + cost_per_unit
        units = min(
            _floor_units(risk_budget / risk_per_unit),
            _floor_units(MAX_NOTIONAL_USD / entry),
            MAX_UNITS,
        )
        if units < 1:
            index += 1
            continue

        direction = Decimal("1") if side == "BUY" else Decimal("-1")
        stop = entry - direction * stop_distance
        target = entry + direction * stop_distance * reward_multiple
        exit_price = data[-1]["close"]
        exit_index = len(data) - 1
        exit_reason = "END_OF_DATA"

        for future_index in range(index, len(data)):
            candle = data[future_index]
            if side == "BUY":
                stop_hit = candle["low"] <= stop
                target_hit = candle["high"] >= target
                if stop_hit:
                    exit_price = min(candle["open"], stop) if candle["open"] < stop else stop
                    exit_index = future_index
                    exit_reason = "STOP"
                    break
                if target_hit:
                    exit_price = target
                    exit_index = future_index
                    exit_reason = "TARGET"
                    break
            else:
                stop_hit = candle["high"] >= stop
                target_hit = candle["low"] <= target
                if stop_hit:
                    exit_price = max(candle["open"], stop) if candle["open"] > stop else stop
                    exit_index = future_index
                    exit_reason = "STOP"
                    break
                if target_hit:
                    exit_price = target
                    exit_index = future_index
                    exit_reason = "TARGET"
                    break

        gross = (exit_price - entry) * Decimal(units) * direction
        costs = cost_per_unit * Decimal(units)
        net = gross - costs
        balance += net
        gross_total += gross
        costs_total += costs
        if net > 0:
            winners += 1
        peak_balance = max(peak_balance, balance)
        drawdown = peak_balance - balance
        if drawdown > max_drawdown:
            max_drawdown = drawdown
            max_drawdown_peak = peak_balance
        trades.append({
            "side": side,
            "entry_epoch": entry_candle["epoch"],
            "exit_epoch": data[exit_index]["epoch"],
            "entry_price": str(entry),
            "exit_price": str(exit_price),
            "units": units,
            "gross_pnl": str(gross.quantize(Decimal("0.01"))),
            "estimated_costs": str(costs.quantize(Decimal("0.01"))),
            "net_pnl": str(net.quantize(Decimal("0.01"))),
            "exit_reason": exit_reason,
        })
        index = exit_index + 1

    net_total = balance - starting
    count = len(trades)
    return {
        "mode": "PAPER",
        "execution": "RESEARCH_ONLY",
        "pair": pair,
        "candles": len(data),
        "lookback": lookback,
        "settings": {
            "risk_percent": str(risk),
            "stop_atr_multiple": str(stop_multiple),
            "reward_risk": str(reward_multiple),
            "estimated_spread_pips": str(spread),
            "maximum_spread_pips": str(max_spread),
            "slippage_pips_per_side": str(slippage),
        },
        "cost_filter": {
            "eligible": liquidity_filter_passed,
            "status": "ASSUMPTION_ONLY",
            "message": "Deriv history has no order-book or bid/ask depth; this is not a live liquidity check.",
        },
        "metrics": {
            "starting_balance": str(starting),
            "ending_balance": str(balance.quantize(Decimal("0.01"))),
            "net_pnl": str(net_total.quantize(Decimal("0.01"))),
            "gross_pnl": str(gross_total.quantize(Decimal("0.01"))),
            "estimated_costs": str(costs_total.quantize(Decimal("0.01"))),
            "return_percent": str((net_total / starting * 100).quantize(Decimal("0.01"))),
            "trade_count": count,
            "win_rate_percent": str((Decimal(winners) / Decimal(count) * 100).quantize(Decimal("0.01"))) if count else None,
            "max_closed_trade_drawdown": str(max_drawdown.quantize(Decimal("0.01"))),
            "max_closed_trade_drawdown_percent": str((max_drawdown / max_drawdown_peak * 100).quantize(Decimal("0.01"))) if max_drawdown_peak else "0",
        },
        "trades": trades[-100:],
        "caveats": [
            "Research output only; no order is submitted and no account state is changed.",
            "Past simulated results do not predict future performance.",
            "Spread and slippage are user assumptions, not measured liquidity or guaranteed execution costs.",
            "Drawdown uses closed-trade equity and excludes intrabar unrealized drawdown.",
            "No ML probability or profitability claim is made.",
        ],
    }
