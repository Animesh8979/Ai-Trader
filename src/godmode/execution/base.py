"""Venue-agnostic execution domain model + the Broker interface.

Both the PaperBroker (simulation — used live-paper and in backtests) and any future
NautilusBroker (real venues) implement `Broker`. The risk engine, router, audit, and
agent layers depend only on this interface, never on a specific engine. Decimal everywhere.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Optional

from godmode.core.money import ZERO, D
from godmode.core.timeutil import utcnow_iso


class Side(str, Enum):
    BUY = "buy"
    SELL = "sell"

    @property
    def sign(self) -> Decimal:
        return D(1) if self is Side.BUY else D(-1)


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"


class OrderStatus(str, Enum):
    NEW = "new"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELED = "canceled"
    REJECTED = "rejected"


def new_client_order_id(prefix: str = "gm") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:20]}"


@dataclass
class Order:
    symbol: str
    side: Side
    order_type: OrderType
    qty: Decimal
    price: Optional[Decimal] = None  # required for LIMIT
    client_order_id: str = field(default_factory=new_client_order_id)
    venue: str = "paper"
    status: OrderStatus = OrderStatus.NEW
    filled_qty: Decimal = ZERO
    avg_fill_price: Decimal = ZERO
    reason: str = ""
    ts_created: str = field(default_factory=utcnow_iso)
    ts_updated: str = field(default_factory=utcnow_iso)

    def __post_init__(self) -> None:
        self.qty = D(self.qty)
        if self.price is not None:
            self.price = D(self.price)
        self.filled_qty = D(self.filled_qty)
        self.avg_fill_price = D(self.avg_fill_price)
        if isinstance(self.side, str):
            self.side = Side(self.side)
        if isinstance(self.order_type, str):
            self.order_type = OrderType(self.order_type)
        if isinstance(self.status, str):
            self.status = OrderStatus(self.status)

    @property
    def remaining_qty(self) -> Decimal:
        return self.qty - self.filled_qty

    @property
    def is_open(self) -> bool:
        return self.status in (OrderStatus.NEW, OrderStatus.PARTIALLY_FILLED)


@dataclass
class Fill:
    symbol: str
    side: Side
    qty: Decimal
    price: Decimal
    fee: Decimal = ZERO
    fee_ccy: str = ""
    client_order_id: str = ""
    realized_pnl: Decimal = ZERO
    ts: str = field(default_factory=utcnow_iso)

    def __post_init__(self) -> None:
        self.qty = D(self.qty)
        self.price = D(self.price)
        self.fee = D(self.fee)
        self.realized_pnl = D(self.realized_pnl)
        if isinstance(self.side, str):
            self.side = Side(self.side)


@dataclass
class Position:
    symbol: str
    qty: Decimal = ZERO          # signed: + long, - short
    avg_price: Decimal = ZERO
    realized_pnl: Decimal = ZERO

    def __post_init__(self) -> None:
        self.qty = D(self.qty)
        self.avg_price = D(self.avg_price)
        self.realized_pnl = D(self.realized_pnl)

    @property
    def is_flat(self) -> bool:
        return self.qty == ZERO

    def market_value(self, mark) -> Decimal:
        return self.qty * D(mark)

    def unrealized_pnl(self, mark) -> Decimal:
        return (D(mark) - self.avg_price) * self.qty


@dataclass
class Account:
    cash: Decimal
    base_currency: str = "USDT"

    def __post_init__(self) -> None:
        self.cash = D(self.cash)


class Broker(ABC):
    """The interface every execution backend implements."""

    @abstractmethod
    def submit_order(self, order: Order) -> Order: ...

    @abstractmethod
    def cancel_order(self, client_order_id: str) -> Optional[Order]: ...

    @abstractmethod
    def get_open_orders(self) -> list[Order]: ...

    @abstractmethod
    def get_positions(self) -> dict[str, Position]: ...

    @abstractmethod
    def get_account(self) -> Account: ...
