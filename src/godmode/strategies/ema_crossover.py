from decimal import Decimal

from pydantic import PositiveInt
from nautilus_trader.trading.strategy import StrategyConfig
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.model.orders import MarketOrder
from nautilus_trader.model.objects import Quantity
from nautilus_trader.indicators.averages import ExponentialMovingAverage

from godmode.strategies.risk_guarded_strategy import RiskGuardedStrategy


class EMACrossoverConfig(StrategyConfig, frozen=True):
    """Configuration for EMACrossover strategy."""

    instrument_id: InstrumentId
    bar_type: BarType
    trade_size: Decimal
    fast_ema_period: PositiveInt = 10
    slow_ema_period: PositiveInt = 20
    close_positions_on_stop: bool = True


class EMACrossover(RiskGuardedStrategy):
    """A simple EMA Crossover strategy that is guarded by the deterministic RiskEngine."""

    def __init__(self, config: EMACrossoverConfig) -> None:
        super().__init__(config)
        self.fast_ema = ExponentialMovingAverage(config.fast_ema_period)
        self.slow_ema = ExponentialMovingAverage(config.slow_ema_period)

    def on_start(self) -> None:
        # Register indicators with the engine for automatic updates on bar events
        self.register_indicator_for_bars(self.config.bar_type, self.fast_ema)
        self.register_indicator_for_bars(self.config.bar_type, self.slow_ema)

        # Subscribe to bar data feed
        self.subscribe_bars(self.config.bar_type)
        self.log.info(f"EMA Crossover strategy started for {self.config.instrument_id}")

    def on_bar(self, bar: Bar) -> None:
        # Check if indicators are warmed up and ready
        if not self.indicators_initialized():
            return

        fast_val = float(self.fast_ema.value)
        slow_val = float(self.slow_ema.value)
        instrument_id = self.config.instrument_id

        # Buy signal (fast crosses slow upwards)
        if fast_val > slow_val:
            if self.portfolio.is_flat(instrument_id):
                self._buy()
            elif self.portfolio.is_net_short(instrument_id):
                self.close_all_positions(instrument_id)
                self._buy()

        # Sell signal (fast crosses slow downwards)
        elif fast_val < slow_val:
            if self.portfolio.is_flat(instrument_id):
                self._sell()
            elif self.portfolio.is_net_long(instrument_id):
                self.close_all_positions(instrument_id)
                self._sell()

    def _buy(self) -> None:
        instrument = self.cache.instrument(self.config.instrument_id)
        qty = instrument.make_qty(self.config.trade_size)

        order: MarketOrder = self.order_factory.market(
            instrument_id=self.config.instrument_id,
            order_side=OrderSide.BUY,
            quantity=qty,
        )
        self.submit_order(order)

    def _sell(self) -> None:
        instrument = self.cache.instrument(self.config.instrument_id)
        qty = instrument.make_qty(self.config.trade_size)

        order: MarketOrder = self.order_factory.market(
            instrument_id=self.config.instrument_id,
            order_side=OrderSide.SELL,
            quantity=qty,
        )
        self.submit_order(order)

    def on_stop(self) -> None:
        if self.config.close_positions_on_stop:
            self.close_all_positions(instrument_id=self.config.instrument_id)
        self.unsubscribe_bars(self.config.bar_type)
        self.log.info("EMA Crossover strategy stopped.")
