"""Read-only Deriv public market-data adapter.

No PAT is needed for public ticks. This module never sends authorize,
buy, sell, proposal, payment, or account commands. It does not update the
authoritative paper-trading state.
"""
import asyncio
import json
import os
from decimal import Decimal, InvalidOperation

ALLOWED_SYMBOLS = frozenset({"frxEURUSD", "frxGBPUSD", "frxUSDJPY"})
PUBLIC_WS_BASE = "wss://ws.derivws.com/websockets/v3"


class DerivMarketDataError(ValueError):
    pass


def tick_request(symbol: str) -> dict:
    if symbol not in ALLOWED_SYMBOLS:
        raise DerivMarketDataError("Unsupported Deriv market symbol")
    return {"ticks": symbol, "subscribe": 0}


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


async def fetch_public_tick(symbol: str) -> dict:
    """Fetch a single public tick; requires configured Deriv App ID."""
    request = tick_request(symbol)
    app_id = os.getenv("DERIV_APP_ID", "")
    if not app_id.isdecimal() or int(app_id) <= 0:
        raise DerivMarketDataError("DERIV_APP_ID must be a registered positive App ID")
    try:
        import websockets
        async with asyncio.timeout(12):
            async with websockets.connect(
                f"{PUBLIC_WS_BASE}?app_id={app_id}",
                open_timeout=8, close_timeout=3, max_size=65536,
            ) as ws:
                await ws.send(json.dumps(request))
                return parse_tick(json.loads(await ws.recv()), symbol)
    except (OSError, TimeoutError, json.JSONDecodeError) as exc:
        raise DerivMarketDataError("Deriv public market feed unavailable") from exc
