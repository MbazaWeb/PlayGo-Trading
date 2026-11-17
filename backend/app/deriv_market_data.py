"""Read-only Deriv public market-data adapter.

No PAT is needed for public ticks. This module never sends authorize,
buy, sell, proposal, payment, or account commands. It does not update the
authoritative paper-trading state.
"""
import asyncio
import json
import re
from decimal import Decimal, InvalidOperation

FOREX_SYMBOL = re.compile(r"frx[A-Z]{6}\Z")
ALLOWED_GRANULARITIES = frozenset(
    {60, 120, 180, 300, 600, 900, 1800, 3600, 7200, 14400, 28800, 86400}
)
MAX_HISTORY_CANDLES = 1000
PUBLIC_WS_URL = "wss://api.derivws.com/trading/v1/options/ws/public"


class DerivMarketDataError(ValueError):
    pass


def _validate_forex_symbol(symbol):
    if not isinstance(symbol, str) or not FOREX_SYMBOL.fullmatch(symbol):
        raise DerivMarketDataError("Unsupported Deriv Forex symbol")


def active_symbols_request() -> dict:
    return {"active_symbols": "brief"}


def parse_active_forex_symbols(message: dict) -> dict:
    if not isinstance(message, dict):
        raise DerivMarketDataError("Invalid Deriv response")
    if message.get("error"):
        raise DerivMarketDataError("Deriv rejected the active markets request")
    if message.get("msg_type") != "active_symbols":
        raise DerivMarketDataError("Deriv active markets response missing")
    rows = message.get("active_symbols")
    if not isinstance(rows, list):
        raise DerivMarketDataError("Invalid Deriv active markets")

    markets = []
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            raise DerivMarketDataError("Invalid Deriv market")
        if str(row.get("market", "")).lower() != "forex":
            continue
        symbol = row.get("underlying_symbol")
        _validate_forex_symbol(symbol)
        name = row.get("underlying_symbol_name")
        if not isinstance(name, str) or not name.strip():
            raise DerivMarketDataError("Invalid Deriv market name")
        open_value = row.get("exchange_is_open")
        suspended_value = row.get("is_trading_suspended")
        if type(open_value) is not int or open_value not in (0, 1):
            raise DerivMarketDataError("Invalid Deriv market status")
        if type(suspended_value) is not int or suspended_value not in (0, 1):
            raise DerivMarketDataError("Invalid Deriv market status")
        try:
            pip_size = Decimal(str(row["pip_size"]))
        except (KeyError, InvalidOperation, TypeError, ValueError):
            raise DerivMarketDataError("Invalid Deriv market precision") from None
        if not pip_size.is_finite() or pip_size <= 0:
            raise DerivMarketDataError("Invalid Deriv market precision")
        if symbol in seen:
            raise DerivMarketDataError("Duplicate Deriv Forex symbol")
        seen.add(symbol)
        markets.append({
            "symbol": symbol,
            "pair": symbol[3:],
            "display_name": name.strip(),
            "pip_size": str(pip_size),
            "exchange_is_open": bool(open_value),
            "is_trading_suspended": bool(suspended_value),
        })
    if not markets:
        raise DerivMarketDataError("No active Deriv Forex markets were returned")
    markets.sort(key=lambda item: item["pair"])
    return {
        "markets": markets,
        "source": "DERIV_PUBLIC",
        "execution": "DISABLED",
    }


def tick_request(symbol: str) -> dict:
    _validate_forex_symbol(symbol)
    return {"ticks": symbol, "subscribe": 0}


def candles_request(symbol: str, *, count: int = 500, granularity: int = 300) -> dict:
    _validate_forex_symbol(symbol)
    if type(count) is not int or not 10 <= count <= MAX_HISTORY_CANDLES:
        raise DerivMarketDataError("Candle count must be between 10 and 1000")
    if type(granularity) is not int or granularity not in ALLOWED_GRANULARITIES:
        raise DerivMarketDataError("Unsupported candle granularity")
    return {
        "ticks_history": symbol,
        "end": "latest",
        "count": count,
        "style": "candles",
        "granularity": granularity,
    }


def parse_tick(message: dict, requested_symbol: str) -> dict:
    if not isinstance(message, dict):
        raise DerivMarketDataError("Invalid Deriv response")
    if message.get("error"):
        raise DerivMarketDataError("Deriv rejected market-data request")
    tick = message.get("tick")
    if message.get("msg_type") != "tick" or not isinstance(tick, dict):
        raise DerivMarketDataError("Deriv tick response missing")
    if tick.get("symbol") != requested_symbol:
        raise DerivMarketDataError("Deriv tick symbol mismatch")
    try:
        quote = Decimal(str(tick["quote"]))
        epoch = int(tick["epoch"])
    except (KeyError, TypeError, ValueError, InvalidOperation) as exc:
        raise DerivMarketDataError("Invalid Deriv tick fields") from exc
    if not quote.is_finite() or quote <= 0 or epoch <= 0:
        raise DerivMarketDataError("Invalid Deriv tick values")
    return {"symbol": requested_symbol, "quote": str(quote),
            "epoch": epoch, "source": "DERIV_PUBLIC", "execution": "DISABLED"}


def parse_candles(message: dict, requested_symbol: str) -> dict:
    if not isinstance(message, dict):
        raise DerivMarketDataError("Invalid Deriv response")
    if message.get("error"):
        raise DerivMarketDataError("Deriv rejected historical-data request")
    if message.get("msg_type") != "candles":
        raise DerivMarketDataError("Deriv candle response missing")
    echo = message.get("echo_req")
    if isinstance(echo, dict) and echo.get("ticks_history", requested_symbol) != requested_symbol:
        raise DerivMarketDataError("Deriv candle symbol mismatch")
    raw_candles = message.get("candles")
    if not isinstance(raw_candles, list) or not 1 <= len(raw_candles) <= MAX_HISTORY_CANDLES:
        raise DerivMarketDataError("Invalid Deriv candle history")

    candles = []
    previous_epoch = 0
    for raw in raw_candles:
        if not isinstance(raw, dict):
            raise DerivMarketDataError("Invalid Deriv candle")
        try:
            epoch = int(raw["epoch"])
            values = {
                name: Decimal(str(raw[name]))
                for name in ("open", "high", "low", "close")
            }
        except (KeyError, TypeError, ValueError, InvalidOperation) as exc:
            raise DerivMarketDataError("Invalid Deriv candle fields") from exc
        if epoch <= previous_epoch or any(not value.is_finite() or value <= 0 for value in values.values()):
            raise DerivMarketDataError("Invalid Deriv candle values")
        if (
            values["high"] < max(values["open"], values["close"], values["low"])
            or values["low"] > min(values["open"], values["close"], values["high"])
        ):
            raise DerivMarketDataError("Inconsistent Deriv candle OHLC values")
        previous_epoch = epoch
        candles.append({"epoch": epoch, **{key: str(value) for key, value in values.items()}})
    return {
        "symbol": requested_symbol,
        "candles": candles,
        "source": "DERIV_PUBLIC",
        "execution": "DISABLED",
    }


async def fetch_public_tick(symbol: str) -> dict:
    """Fetch a single public tick over Deriv's unauthenticated public endpoint."""
    request = tick_request(symbol)
    try:
        import websockets
        from websockets.exceptions import WebSocketException
    except ModuleNotFoundError as exc:
        raise DerivMarketDataError("WebSocket client dependency unavailable") from exc
    try:
        async with asyncio.timeout(12):
            async with websockets.connect(
                PUBLIC_WS_URL,
                open_timeout=8, close_timeout=3, max_size=65536,
            ) as ws:
                await ws.send(json.dumps(request))
                return parse_tick(json.loads(await ws.recv()), symbol)
    except (OSError, TimeoutError, json.JSONDecodeError, WebSocketException) as exc:
        raise DerivMarketDataError("Deriv public market feed unavailable") from exc


async def fetch_public_candles(
    symbol: str,
    *,
    count: int = 500,
    granularity: int = 300,
) -> dict:
    """Fetch read-only historical candles; no trading command is sent."""
    request = candles_request(symbol, count=count, granularity=granularity)
    try:
        import websockets
        from websockets.exceptions import WebSocketException
        async with asyncio.timeout(12):
            async with websockets.connect(
                PUBLIC_WS_URL,
                open_timeout=8, close_timeout=3, max_size=65536,
            ) as ws:
                await ws.send(json.dumps(request))
                message = json.loads(await ws.recv())
    except (
        OSError,
        TimeoutError,
        json.JSONDecodeError,
        WebSocketException,
    ) as exc:
        raise DerivMarketDataError("Deriv historical-data feed unavailable") from exc
    return parse_candles(message, symbol)


async def fetch_public_forex_markets() -> dict:
    """Fetch Deriv's active Forex catalog for the read-only market view."""
    try:
        import websockets
        from websockets.exceptions import WebSocketException
        async with asyncio.timeout(12):
            async with websockets.connect(
                PUBLIC_WS_URL,
                open_timeout=8, close_timeout=3, max_size=262144,
            ) as ws:
                await ws.send(json.dumps(active_symbols_request()))
                message = json.loads(await ws.recv())
    except (
        OSError,
        TimeoutError,
        json.JSONDecodeError,
        WebSocketException,
    ) as exc:
        raise DerivMarketDataError("Deriv Forex market catalog unavailable") from exc
    return parse_active_forex_symbols(message)
