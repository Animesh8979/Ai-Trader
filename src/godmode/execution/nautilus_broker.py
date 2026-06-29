from decimal import Decimal
from typing import Dict, List, Optional

from godmode.execution.base import Account, Broker, Order, OrderStatus, OrderType, Position, Side
from godmode.core.money import D


class NautilusBrokerAdapter(Broker):
    """Adapter wrapping NautilusTrader strategy/portfolio context as a unified Godmode Broker."""

    def __init__(self, nautilus_strategy) -> None:
        self.strategy = nautilus_strategy

    def submit_order(self, order: Order) -> Order:
        from nautilus_trader.model.enums import OrderSide
        
        instrument = self.strategy.cache.instrument(self.strategy.config.instrument_id)
        qty = instrument.make_qty(float(order.qty))
        side = OrderSide.BUY if order.side == Side.BUY else OrderSide.SELL

        if order.order_type == OrderType.LIMIT:
            if order.price is None:
                raise ValueError("Limit price must be specified for limit orders.")
            naut_order = self.strategy.order_factory.limit(
                instrument_id=instrument.id,
                order_side=side,
                quantity=qty,
                price=instrument.make_price(float(order.price)),
            )
        else:
            naut_order = self.strategy.order_factory.market(
                instrument_id=instrument.id,
                order_side=side,
                quantity=qty,
            )

        self.strategy.submit_order(naut_order)
        order.client_order_id = str(naut_order.client_order_id)
        return order

    def cancel_order(self, client_order_id: str) -> Optional[Order]:
        from nautilus_trader.model.identifiers import ClientOrderId

        try:
            cid = ClientOrderId(client_order_id)
            # Retrieve open order from cache
            naut_order = self.strategy.cache.order(client_order_id=cid)
            if naut_order and naut_order.is_open:
                self.strategy.cancel_order(naut_order)
                return Order(
                    symbol=str(naut_order.instrument_id),
                    side=Side.BUY if naut_order.side.name == "BUY" else Side.SELL,
                    order_type=OrderType.LIMIT if naut_order.type.name == "LIMIT" else OrderType.MARKET,
                    qty=Decimal(str(float(naut_order.quantity))),
                    client_order_id=str(naut_order.client_order_id),
                    status=OrderStatus.CANCELED,
                )
        except Exception as exc:
            self.strategy.log.debug(f"Failed to cancel order {client_order_id} in NautilusBrokerAdapter: {exc}")
        return None

    def get_open_orders(self) -> List[Order]:
        orders = []
        try:
            naut_orders = self.strategy.cache.orders()
            for o in naut_orders:
                if o.is_open:
                    orders.append(
                        Order(
                            symbol=str(o.instrument_id),
                            side=Side.BUY if o.side.name == "BUY" else Side.SELL,
                            order_type=OrderType.LIMIT if o.type.name == "LIMIT" else OrderType.MARKET,
                            qty=Decimal(str(float(o.quantity))),
                            price=Decimal(str(float(o.price))) if hasattr(o, "price") and o.price is not None else None,
                            client_order_id=str(o.client_order_id),
                            status=OrderStatus.NEW,
                        )
                    )
        except Exception as exc:
            self.strategy.log.debug(f"Failed to query open orders in NautilusBrokerAdapter: {exc}")
        return orders

    def get_positions(self) -> Dict[str, Position]:
        positions = {}
        try:
            naut_positions = self.strategy.cache.positions()
            for pos in naut_positions:
                if pos.is_open:
                    symbol = str(pos.instrument_id)
                    positions[symbol] = Position(
                        symbol=symbol,
                        qty=Decimal(str(float(pos.signed_qty))),
                        avg_price=Decimal(str(float(pos.avg_px_open))),
                        realized_pnl=Decimal(str(float(pos.realized_pnl))),
                    )
        except Exception as exc:
            self.strategy.log.debug(f"Failed to query positions in NautilusBrokerAdapter: {exc}")
        return positions

    def get_account(self) -> Account:
        cash = Decimal("0")
        try:
            accounts = self.strategy.cache.accounts()
            for acct in accounts:
                cash += Decimal(str(float(acct.free)))
        except Exception:
            try:
                eq = self.strategy.portfolio.equity()
                if eq is not None:
                    cash = Decimal(str(float(eq)))
            except Exception:
                pass
        return Account(cash=cash)
