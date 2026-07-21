"""Execution & venue adapters.

Phase 0 ships a light ccxt-based connectivity adapter (for the smoke test). Phase 1
brings in NautilusTrader as the production event-driven core, where the *same* strategy
code runs in backtest, paper, and live with no look-ahead bias. Includes idempotent
order submission and a broker-state reconciliation loop.
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
    "NautilusBrokerAdapter",
    "CryptoCcxtAdapter",
    "LiveRunner",
]

