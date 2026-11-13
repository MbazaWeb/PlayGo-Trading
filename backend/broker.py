"""Broker integration boundary. No live execution implementation is present.

Only read-only market-data adapters may be used during research. A broker
credential or environment variable cannot enable real-money orders.
"""
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Protocol


class TradingMode(str, Enum):
    PAPER = "PAPER"
    LIVE = "LIVE"


class BrokerUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class BrokerCapabilities:
    provider: str
    market_data: bool
    demo_orders: bool
    live_orders: bool
    supported_pairs: tuple[str, ...]


class BrokerAdapter(Protocol):
    """Future adapter interface; deliberately excludes live order submission."""
    def capabilities(self) -> BrokerCapabilities: ...
    def quote(self, pair: str) -> dict: ...


class PaperOnlyBroker:
    def capabilities(self) -> BrokerCapabilities:
        return BrokerCapabilities(
            provider="INTERNAL_PAPER", market_data=True, demo_orders=True,
            live_orders=False, supported_pairs=("EURUSD", "GBPUSD"),
        )

    def quote(self, pair: str) -> dict:
        raise BrokerUnavailable("Quotes are supplied by the existing paper feed; no broker order route exists.")


def execution_policy() -> dict:
    """Fail-closed capability report, independent of environment configuration."""
    capabilities = PaperOnlyBroker().capabilities()
    return {
        "mode": TradingMode.PAPER.value,
        "real_money_enabled": False,
        "broker": asdict(capabilities),
        "live_order_submission": "NOT_IMPLEMENTED",
        "approval_required": True,
    }


def reject_live_execution(*_args: object, **_kwargs: object) -> None:
    raise BrokerUnavailable(
        "Real-money execution is unavailable. Broker certification, security "
        "review, capital authorization, and audited risk controls are required."
    )
