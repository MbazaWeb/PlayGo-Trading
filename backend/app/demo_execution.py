
"""Deterministic, network-free demo execution simulator.

This module never connects to a broker and cannot place real orders.
A production adapter must not reuse its in-memory idempotency mechanism.

Supported instruments:
    EURUSD
    GBPUSD

Execution:
    BUY  = Ask + adverse slippage
    SELL = Bid - adverse slippage

All orders are simulated.
"""

from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from typing import Literal


ALLOWED_PAIRS = frozenset(("EURUSD", "GBPUSD"))

PIP_SIZE = Decimal("0.0001")
PRICE_PRECISION = Decimal("0.00001")
USD_PRECISION = Decimal("0.01")

MIN_UNITS = 1
MAX_UNITS = 100_000
MAX_ORDER_ID_LENGTH = 128

MIN_SLIPPAGE = Decimal("0")
MAX_SLIPPAGE = Decimal("5")


class DemoOrderError(ValueError):
    """Raised when a simulated order fails validation."""


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
    """Deterministic, isolated simulated execution engine.

    Guarantees within one engine instance:
        - No broker connections
        - No real orders
        - Validated order inputs
        - Deterministic fill calculations
        - Duplicate-order protection
        - Conflicting order-ID rejection

    Persistent PostgreSQL idempotency is managed separately
    by postgres_demo_orders.py.
    """

    def __init__(self, slippage_pips: str = "0.2") -> None:
        self.slippage = self._decimal(slippage_pips)

        if not MIN_SLIPPAGE <= self.slippage <= MAX_SLIPPAGE:
            raise DemoOrderError(
                "Slippage must be between 0 and 5 pips"
            )

        self._orders: dict[str, tuple[tuple, DemoFill]] = {}

    @staticmethod
    def _decimal(value: str | float | Decimal) -> Decimal:
        """Convert a value into a finite Decimal."""

        if isinstance(value, bool):
            raise DemoOrderError("Invalid numeric value")

        try:
            number = Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError) as exc:
            raise DemoOrderError("Invalid numeric value") from exc

        if not number.is_finite():
            raise DemoOrderError("Non-finite numeric value")

        return number

    @staticmethod
    def _validate_order_id(client_order_id: str) -> None:
        """Validate client order identifiers."""

        if not isinstance(client_order_id, str):
            raise DemoOrderError(
                "Client order ID must be a string"
            )

        if not client_order_id:
            raise DemoOrderError(
                "Client order ID is required"
            )

        if client_order_id != client_order_id.strip():
            raise DemoOrderError(
                "Client order ID cannot contain surrounding whitespace"
            )

        if len(client_order_id) > MAX_ORDER_ID_LENGTH:
            raise DemoOrderError(
                "Client order ID exceeds 128 characters"
            )

        if any(ord(char) < 32 or ord(char) == 127 for char in client_order_id):
            raise DemoOrderError(
                "Client order ID contains invalid control characters"
            )

    @staticmethod
    def _validate_instrument(pair: str, side: str) -> None:
        """Validate instrument and trade direction."""

        if pair not in ALLOWED_PAIRS:
            raise DemoOrderError(
                "Unsupported demo instrument"
            )

        if side not in ("BUY", "SELL"):
            raise DemoOrderError(
                "Unsupported demo order direction"
            )

    @staticmethod
    def _validate_units(units: int) -> None:
        """Validate simulated order quantity."""

        if (
            isinstance(units, bool)
            or not isinstance(units, int)
            or not MIN_UNITS <= units <= MAX_UNITS
        ):
            raise DemoOrderError(
                "Demo quantity must be an integer between 1 and 100000"
            )

    def execute(
        self,
        *,
        client_order_id: str,
        pair: str,
        side: str,
        units: int,
        bid: str | float,
        ask: str | float,
    ) -> dict:
        """Validate and execute a simulated market order.

        No network requests or database writes occur.
        """

        # 1. Validate order parameters.
        self._validate_order_id(client_order_id)
        self._validate_instrument(pair, side)
        self._validate_units(units)

        # 2. Validate market quotes.
        b = self._decimal(bid)
        a = self._decimal(ask)

        if b <= 0 or a <= b:
            raise DemoOrderError(
                "Invalid bid/ask quote"
            )

        # 3. Construct deterministic request fingerprint.
        fingerprint = (
            pair,
            side,
            units,
            str(b),
            str(a),
            str(self.slippage),
        )

        # 4. Enforce in-memory idempotency.
        existing = self._orders.get(client_order_id)

        if existing is not None:
            previous_fingerprint, previous_fill = existing

            if previous_fingerprint != fingerprint:
                raise DemoOrderError(
                    "Idempotency key reused for a different request"
                )

            return asdict(previous_fill)

        # 5. Determine requested execution price.
        requested_price = a if side == "BUY" else b

        # 6. Calculate adverse slippage.
        slippage_amount = self.slippage * PIP_SIZE

        if side == "BUY":
            fill_price = requested_price + slippage_amount
        else:
            fill_price = requested_price - slippage_amount

        if fill_price <= 0:
            raise DemoOrderError(
                "Calculated fill price must be positive"
            )

        # 7. Normalize simulated execution price.
        filled_price = fill_price.quantize(PRICE_PRECISION)

        if filled_price <= 0:
            raise DemoOrderError(
                "Calculated fill price is invalid at supported precision"
            )

        # 8. Calculate estimated bid/ask spread cost.
        spread = a - b

        spread_cost_usd = (
            spread * Decimal(units)
        ).quantize(USD_PRECISION)

        # 9. Generate deterministic execution ID.
        execution_id = sha256(
            ("DEMO:" + client_order_id).encode("utf-8")
        ).hexdigest()[:24]

        # 10. Build immutable simulated fill.
        fill = DemoFill(
            client_order_id=client_order_id,
            execution_id=execution_id,
            pair=pair,
            side=side,
            units=units,
            requested_price=str(requested_price),
            filled_price=str(filled_price),
            slippage_pips=str(self.slippage),
            estimated_spread_cost_usd=str(spread_cost_usd),
        )

        # 11. Cache the simulated order for idempotent retries.
        self._orders[client_order_id] = (
            fingerprint,
            fill,
        )

        return asdict(fill)
