from decimal import Decimal
from typing import Optional
import json
import threading

from pydantic import PositiveInt
from nautilus_trader.trading.strategy import StrategyConfig
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.orders import MarketOrder
from nautilus_trader.indicators.averages import ExponentialMovingAverage
from nautilus_trader.indicators.rsi import RelativeStrengthIndex

from godmode.strategies.risk_guarded_strategy import RiskGuardedStrategy
from godmode.agents.brain import MultiAgentBrain


class MultiAgentStrategyConfig(StrategyConfig, frozen=True):
    """Configuration for MultiAgentStrategy."""

    instrument_id: InstrumentId
    bar_type: BarType
    trade_size: Decimal
    rsi_period: PositiveInt = 14
    fast_ema_period: PositiveInt = 10
    slow_ema_period: PositiveInt = 20
    close_positions_on_stop: bool = True


class MultiAgentStrategy(RiskGuardedStrategy):
    """A strategy that makes trading decisions by querying a MultiAgentBrain."""

    def __init__(self, config: MultiAgentStrategyConfig) -> None:
        super().__init__(config)
        self.brain = MultiAgentBrain()
        self.rsi = RelativeStrengthIndex(config.rsi_period)
        self.ema_fast = ExponentialMovingAverage(config.fast_ema_period)
        self.ema_slow = ExponentialMovingAverage(config.slow_ema_period)
        self._latest_target = "hold"
        self._is_thinking = False

    def on_start(self) -> None:
        self.register_indicator_for_bars(self.config.bar_type, self.rsi)
        self.register_indicator_for_bars(self.config.bar_type, self.ema_fast)
        self.register_indicator_for_bars(self.config.bar_type, self.ema_slow)
        self.subscribe_bars(self.config.bar_type)
        self.log.info(f"Multi-Agent strategy started for {self.config.instrument_id}")

    def on_bar(self, bar: Bar) -> None:
        if not self.indicators_initialized():
            return

        instrument_id = self.config.instrument_id

        # 1. Execute based on the LATEST known target state from the background thread
        action = self._latest_target
        if action == "buy":
            if self.portfolio.is_flat(instrument_id):
                self._buy()
            elif self.portfolio.is_net_short(instrument_id):
                self.close_all_positions(instrument_id)
                self._buy()
        elif action == "sell":
            if self.portfolio.is_flat(instrument_id):
                self._sell()
            elif self.portfolio.is_net_long(instrument_id):
                self.close_all_positions(instrument_id)
                self._sell()
        
        # Reset target after execution attempt
        self._latest_target = "hold"

        # 2. If the brain is idle, spawn a background thread to process this new bar
        if not self._is_thinking:
            # Compile price data - removing float casts to preserve exact strings
            price_data = {
                "open": str(bar.open),
                "high": str(bar.high),
                "low": str(bar.low),
                "close": str(bar.close),
                "volume": str(bar.volume),
                "rsi": str(self.rsi.value),
                "ema_fast": str(self.ema_fast.value),
                "ema_slow": str(self.ema_slow.value),
            }

            # Compile portfolio state
            portfolio_state = {
                "timestamp": bar.ts.to_iso8601() if hasattr(bar.ts, "to_iso8601") else str(bar.ts),
                "equity": str(self.portfolio.equity() or 0.0),
                "cash": str(self.portfolio.cash_balance(instrument_id.venue) or 0.0),
                "position_size": str(self.portfolio.net_position(instrument_id).signed_qty) if self.portfolio.net_position(instrument_id) else "0.0",
            }

            # Simulated News Headlines
            news_feed = [
                "Federal Reserve hints at interest rate stability in upcoming quarter.",
                f"Trading volume surges for {instrument_id} as institutional interest rises.",
                "Market volatility stabilizes following options expiry week.",
            ]

            self._is_thinking = True
            threading.Thread(
                target=self._run_brain, 
                args=(instrument_id, price_data, portfolio_state, news_feed), 
                daemon=True
            ).start()

    def _run_brain(self, instrument_id, price_data, portfolio_state, news_feed) -> None:
        try:
            proposal = self.brain.decide_trade(
                symbol=str(instrument_id),
                price_data=price_data,
                portfolio_state=portfolio_state,
                news_feed=news_feed,
            )
            self._latest_target = proposal.get("action", "hold").lower()
        except Exception as exc:
            self.log.error(f"MultiAgentBrain debate cycle failed: {exc}")
        finally:
            self._is_thinking = False

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
        self.log.info("Multi-Agent strategy stopped.")
