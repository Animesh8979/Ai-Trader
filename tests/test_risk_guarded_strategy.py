import sys
import importlib
from decimal import Decimal
from unittest.mock import MagicMock, patch

# 1. Define python mock classes for the Cython base class Strategy
class MockStrategy:
    def __init__(self, config):
        self.config = config
        self.portfolio = MagicMock()
        self.cache = MagicMock()
        self.order_factory = MagicMock()
        self.log = MagicMock()
        
    def submit_order(self, order, position_id=None, client_id=None, params=None):
        pass

class MockStrategyConfig:
    def __init_subclass__(cls, *args, **kwargs):
        pass

# 2. Mock the module imports
sys.modules["nautilus_trader.trading.strategy"] = MagicMock(
    Strategy=MockStrategy,
    StrategyConfig=MockStrategyConfig
)

# 3. Reload the module under test
import godmode.strategies.risk_guarded_strategy
importlib.reload(godmode.strategies.risk_guarded_strategy)

from godmode.strategies.risk_guarded_strategy import RiskGuardedStrategy
from godmode.risk.engine import Verdict, RiskDecision
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.objects import Quantity
from nautilus_trader.model.identifiers import InstrumentId
import pytest

@pytest.fixture
def mock_strategy():
    config = MagicMock()
    config.instrument_id = InstrumentId.from_str("BTCUSDT.BINANCE")
    
    strategy = RiskGuardedStrategy(config)
    strategy.portfolio = MagicMock()
    strategy.cache = MagicMock()
    strategy.order_factory = MagicMock()
    strategy.log = MagicMock()
    return strategy


def test_submit_order_blocked_by_kill_switch(mock_strategy):
    mock_strategy.kill_switch = MagicMock()
    mock_strategy.kill_switch.is_halted.return_value = True

    order = MagicMock()
    order.instrument_id = InstrumentId.from_str("BTCUSDT.BINANCE")

    with patch.object(MockStrategy, "submit_order") as mock_super_submit:
        mock_strategy.submit_order(order)
        mock_super_submit.assert_not_called()
        mock_strategy.log.error.assert_called_with(
            "BLOCKED order for BTCUSDT.BINANCE: kill switch is engaged."
        )


def test_submit_order_clamped(mock_strategy):
    mock_strategy.kill_switch = MagicMock()
    mock_strategy.kill_switch.is_halted.return_value = False

    order = MagicMock()
    order.instrument_id = InstrumentId.from_str("BTCUSDT.BINANCE")
    order.side = OrderSide.BUY
    order.quantity = Quantity(1.0, 4)
    order.price = 50000.0

    mock_strategy.risk_engine = MagicMock()
    mock_strategy.risk_engine.evaluate_and_enforce.return_value = RiskDecision(
        verdict=Verdict.CLAMP,
        approved_qty=Decimal("0.4"),
        reasons=["clamped by exposure limit"],
    )

    with patch.object(MockStrategy, "submit_order") as mock_super_submit:
        mock_strategy.submit_order(order)
        assert float(order.quantity) == 0.4
        mock_super_submit.assert_called_once_with(order, position_id=None, client_id=None, params=None)


def test_submit_order_rejected(mock_strategy):
    mock_strategy.kill_switch = MagicMock()
    mock_strategy.kill_switch.is_halted.return_value = False

    order = MagicMock()
    order.instrument_id = InstrumentId.from_str("BTCUSDT.BINANCE")
    order.side = OrderSide.BUY
    order.quantity = Quantity(1.0, 4)
    order.price = 50000.0

    mock_strategy.risk_engine = MagicMock()
    mock_strategy.risk_engine.evaluate_and_enforce.return_value = RiskDecision(
        verdict=Verdict.REJECT,
        approved_qty=Decimal("0"),
        reasons=["drawdown limit reached"],
    )

    with patch.object(MockStrategy, "submit_order") as mock_super_submit:
        mock_strategy.submit_order(order)
        mock_super_submit.assert_not_called()
        mock_strategy.log.error.assert_called_with(
            "REJECTED order for BTCUSDT.BINANCE: drawdown limit reached"
        )
