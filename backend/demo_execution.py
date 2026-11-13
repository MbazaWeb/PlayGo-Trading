"""Deterministic, network-free demo execution simulator.

This module never connects to a broker and cannot place real orders.
A production adapter must not reuse its in-memory idempotency mechanism.
"""
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from typing import Literal

ALLOWED_PAIRS = frozenset(("EURUSD", "GBPUSD"))


class DemoOrderError(ValueError):
    pass


@dataclass(frozen=True)
class DemoFill:
    client_order_id: str
    execution_id: str
    pair: str
    side: str
    units: int
    requested_price: str
    filled_price: str
    slippage_pips: str
    estimated_spread_cost_usd: str
    status: Literal["FILLED"] = "FILLED"
    mode: Literal["DEMO"] = "DEMO"


class DemoExecutionEngine:
    """Isolated instance for reproducible simulated fills and duplicate protection."""

    def __init__(self, slippage_pips: str = "0.2") -> None:
        self.slippage = self._decimal(slippage_pips)
        if self.slippage < 0 or self.slippage > 5:
            raise DemoOrderError("Slippage must be between 0 and 5 pips")
        self._orders: dict[str, tuple[tuple, DemoFill]] = {}

    @staticmethod
    def _decimal(value: str | float | Decimal) -> Decimal:
        try:
            number = Decimal(str(value))
        except (InvalidOperation, ValueError) as exc:
            raise DemoOrderError("Invalid price") from exc
        if not number.is_finite():
            raise DemoOrderError("Non-finite price")
        return number

    def execute(self, *, client_order_id: str, pair: str, side: str,
                units: int, bid: str | float, ask: str | float) -> dict:
        if not client_order_id or len(client_order_id) > 128:
            raise DemoOrderError("Client order ID required (maximum 128 characters)")
        if pair not in ALLOWED_PAIRS or side not in ("BUY", "SELL"):
            raise DemoOrderError("Unsupported demo instrument or side")
        if isinstance(units, bool) or not isinstance(units, int) or not 1 <= units <= 100000:
            raise DemoOrderError("Invalid demo quantity")
        b, a = self._decimal(bid), self._decimal(ask)
        if b <= 0 or a <= b:
            raise DemoOrderError("Invalid bid/ask quote")
        pip = Decimal("0.0001")
        fingerprint = (pair, side, units, str(b), str(a))
        existing = self._orders.get(client_order_id)
        if existing:
            if existing[0] != fingerprint:
                raise DemoOrderError("Idempotency key reused for a different request")
            return asdict(existing[1])
        requested = a if side == "BUY" else b
        fill_price = requested + self.slippage * pip * (1 if side == "BUY" else -1)
        fill = DemoFill(
            client_order_id=client_order_id,
            execution_id=sha256(("DEMO:" + client_order_id).encode()).hexdigest()[:24],
            pair=pair, side=side, units=units,
            requested_price=str(requested),
            filled_price=str(fill_price.quantize(Decimal("0.00001"))),
            slippage_pips=str(self.slippage),
            estimated_spread_cost_usd=str(((a-b)*units).quantize(Decimal("0.01"))),
        )
        self._orders[client_order_id] = (fingerprint, fill)
        return asdict(fill)
