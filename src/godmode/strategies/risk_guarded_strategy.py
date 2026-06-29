from decimal import Decimal
from typing import Optional

from nautilus_trader.trading.strategy import Strategy, StrategyConfig
from nautilus_trader.model.orders import Order
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.identifiers import InstrumentId

from godmode.risk.engine import RiskEngine, OrderProposal, PortfolioState, Verdict
from godmode.core.killswitch import get_kill_switch
from godmode.core.logging import get_logger

log = get_logger("strategies.risk_guarded")


class RiskGuardedStrategy(Strategy):
    """Base class strategy that intercepts orders and evaluates them against the RiskEngine."""

    def __init__(self, config: StrategyConfig) -> None:
        super().__init__(config)
        self.risk_engine = RiskEngine()
        self.kill_switch = get_kill_switch()
        self._peak_equity: Optional[Decimal] = None

    def submit_order(self, order: Order, position_id=None, client_id=None, params=None) -> None:
        """Intercept order submission and enforce deterministic risk constraints."""
        # 1. Enforce physical kill switch on disk
        if self.kill_switch.is_halted():
            self.log.error(f"BLOCKED order for {order.instrument_id}: kill switch is engaged.")
            return

        # 2. Extract order proposal details
        symbol = str(order.instrument_id)
        side = "buy" if order.side == OrderSide.BUY else "sell"
        qty = Decimal(str(order.quantity))
        
        # Determine limit price or fallback to last known price
        price = Decimal("0")
        if hasattr(order, "price") and order.price is not None:
            price = Decimal(str(order.price))
        else:
            # For market orders, fetch the last trade or quote price from cache
            try:
                last_tick = self.cache.quote_tick(order.instrument_id)
                if last_tick is not None:
                    price = Decimal(str(float((last_tick.ask_price + last_tick.bid_price) / 2)))
                else:
                    last_trade = self.cache.trade_tick(order.instrument_id)
                    if last_trade is not None:
                        price = Decimal(str(float(last_trade.price)))
                    elif hasattr(self.config, "bar_type"):
                        last_bar = self.cache.bar(self.config.bar_type)
                        if last_bar is not None:
                            price = Decimal(str(float(last_bar.close)))
            except Exception as exc:
                self.log.debug(f"Failed to fetch cache price for {symbol}: {exc}")
            
            if price <= 0:
                price = Decimal("1.0")  # safe fallback

        # Determine if this order is reducing risk
        is_reducing = False
        net_qty = Decimal("0")
        try:
            position = self.portfolio.net_position(order.instrument_id)
            if position is not None:
                net_qty = Decimal(str(float(position.signed_qty)))
        except Exception:
            pass

        if (net_qty > 0 and side == "sell") or (net_qty < 0 and side == "buy"):
            is_reducing = True

        proposal = OrderProposal(
            symbol=symbol,
            side=side,
            qty=qty,
            price=price,
            order_type="limit" if hasattr(order, "price") and order.price is not None else "market",
            is_reducing=is_reducing,
        )

        # 3. Extract state for the risk engine
        current_equity = self._get_portfolio_equity()
        if self._peak_equity is None or current_equity > self._peak_equity:
            self._peak_equity = current_equity

        # Gross exposure: sum of open position values
        gross_exposure = Decimal("0")
        open_positions_count = 0
        has_position_in_symbol = False
        try:
            open_positions = [pos for pos in self.cache.positions(instrument_id=order.instrument_id) if pos.is_open]
            has_position_in_symbol = len(open_positions) > 0
            
            all_open_positions = [pos for pos in self.cache.positions() if pos.is_open]
            open_positions_count = len(all_open_positions)
            for pos in all_open_positions:
                gross_exposure += Decimal(str(float(pos.quantity))) * Decimal(str(float(pos.avg_px_open)))
        except Exception as exc:
            self.log.debug(f"Failed to read cache positions for exposure: {exc}")

        # Realized PnL of the day (best effort fallback sum)
        day_realized_pnl = Decimal("0")
        try:
            pnl_dict = self.portfolio.realized_pnls()
            if pnl_dict:
                day_realized_pnl = sum(Decimal(str(float(val))) for val in pnl_dict.values())
        except Exception:
            pass

        portfolio_state = PortfolioState(
            equity=current_equity,
            peak_equity=self._peak_equity,
            day_realized_pnl=day_realized_pnl,
            gross_exposure=gross_exposure,
            open_positions=open_positions_count,
            has_position_in_symbol=has_position_in_symbol,
        )

        # 4. Evaluate against the Risk Engine
        decision = self.risk_engine.evaluate_and_enforce(proposal, portfolio_state, self.kill_switch)

        # 5. Handle verdict
        if decision.verdict == Verdict.REJECT:
            self.log.error(f"REJECTED order for {symbol}: {', '.join(decision.reasons)}")
            return
        elif decision.verdict == Verdict.CLAMP:
            self.log.warn(f"CLAMPED order for {symbol}: {', '.join(decision.reasons)}")
            # Modify the order quantity to the approved quantity
            from nautilus_trader.model.objects import Quantity
            # NautilusTrader Quantity objects are double-precision internally, so we construct it
            # matching the original order's precision or default scale.
            approved_qty_float = float(decision.approved_qty)
            order.quantity = Quantity(approved_qty_float, order.quantity.precision)

        # Forward the approved/clamped order to the execution engine
        super().submit_order(order, position_id=position_id, client_id=client_id, params=params)

    def _get_portfolio_equity(self) -> Decimal:
        """Safely fetch portfolio equity, with fallback to config."""
        try:
            eq = self.portfolio.equity()
            if eq is not None:
                return Decimal(str(float(eq)))
        except Exception:
            pass

        # Fallback to summing up cash balances from cache
        try:
            accounts = self.cache.accounts()
            if accounts:
                total_bal = Decimal("0")
                for acct in accounts:
                    total_bal += Decimal(str(float(acct.total)))
                return total_bal
        except Exception:
            pass

        # Sane ultimate fallback
        from godmode.core.config import load_config
        return Decimal(str(load_config().app.paper_starting_equity))
