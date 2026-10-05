"""Make `godmode` importable when running tests without an editable install."""

import pathlib
import sys

SRC = pathlib.Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _install_nautilus_stubs() -> None:
    """Stub nautilus_trader with minimal fakes when the heavy dependency is not
    installed, so strategy unit tests can import and subclass it. If the real
    package is present it is used untouched.
    """
    import importlib.util
    import types

    if importlib.util.find_spec("nautilus_trader") is not None:
        return

    root = types.ModuleType("nautilus_trader")

    model = types.ModuleType("nautilus_trader.model")

    enums = types.ModuleType("nautilus_trader.model.enums")

    class OrderSide:
        BUY = "BUY"
        SELL = "SELL"

    enums.OrderSide = OrderSide

    objects = types.ModuleType("nautilus_trader.model.objects")

    class Quantity:
        def __init__(self, value, precision: int = 8):
            self.value = value
            self.precision = int(precision)

        def __float__(self):
            return float(self.value)

        def __str__(self):
            return str(self.value)

    objects.Quantity = Quantity

    identifiers = types.ModuleType("nautilus_trader.model.identifiers")

    class InstrumentId:
        def __init__(self, value: str):
            self.value = str(value)

        @classmethod
        def from_str(cls, raw: str) -> "InstrumentId":
            return cls(raw)

        def __str__(self):
            return self.value

    identifiers.InstrumentId = InstrumentId

    trading = types.ModuleType("nautilus_trader.trading")
    strategy_mod = types.ModuleType("nautilus_trader.trading.strategy")

    class Strategy:
        def __init__(self, config=None):
            self.config = config

        def submit_order(self, order, position_id=None, client_id=None, params=None):
            raise NotImplementedError

    class StrategyConfig:
        pass

    strategy_mod.Strategy = Strategy
    strategy_mod.StrategyConfig = StrategyConfig

    model.enums = enums
    model.objects = objects
    model.identifiers = identifiers
    trading.strategy = strategy_mod
    root.model = model
    root.trading = trading

    sys.modules["nautilus_trader"] = root
    sys.modules["nautilus_trader.model"] = model
    sys.modules["nautilus_trader.model.enums"] = enums
    sys.modules["nautilus_trader.model.objects"] = objects
    sys.modules["nautilus_trader.model.identifiers"] = identifiers
    sys.modules["nautilus_trader.trading"] = trading
    sys.modules["nautilus_trader.trading.strategy"] = strategy_mod


_install_nautilus_stubs()
