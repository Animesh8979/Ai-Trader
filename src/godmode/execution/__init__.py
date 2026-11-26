"""Execution & venue adapters.

Provides CCXT crypto testnet connectivity, Indian broker adapter scaffolding,
idempotent client order IDs, post-only pegging helpers, and the async live/paper runner.
"""

from godmode.execution.base import Broker, Order, Fill, Position, Account, Side, OrderType, OrderStatus
from godmode.execution.adapter import BaseBrokerAdapter
from godmode.execution.crypto_ccxt import CryptoCcxtAdapter
from godmode.execution.indian_broker_adapter import ShoonyaAdapter
from godmode.execution.live_runner import LiveRunner

__all__ = [
    "Broker",
    "Order",
    "Fill",
    "Position",
    "Account",
    "Side",
    "OrderType",
    "OrderStatus",
    "BaseBrokerAdapter",
    "CryptoCcxtAdapter",
    "ShoonyaAdapter",
    "LiveRunner",
]

