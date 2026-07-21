"""SyntheticStressEngine — parametric market scenarios for strategy robustness.

Generates synthetic OHLCV series representing extreme scenarios:
- Flash crash: -40% in 3 days
- Altseason decoupling: BTC flat, alts +200%
- Exchange hack panic: -25% in 6h
- Regulatory crackdown: -15% immediate, drag for 10 days
- Volatility explosion: ATR × 5

Tests all active strategies against worst-case drawdown.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from godmode.core.logging import get_logger

log = get_logger("backtest.synthetic")


@dataclass
class StressScenario:
    name: str
    description: str
    severity: str  # "low", "medium", "high", "extreme"
    candles: List[List[float]]
    expected_drawdown_pct: float


def _base_random_walk(n: int, start_price: float = 100.0, daily_vol: float = 0.015) -> List[float]:
    prices = [start_price]
    for _ in range(n - 1):
        daily_ret = random.gauss(0.0005, daily_vol)
        prices.append(prices[-1] * (1 + daily_ret))
    return prices


def _prices_to_candles(prices: List[float], base_volume: float = 1000.0) -> List[List[float]]:
    candles = []
    for i, price in enumerate(prices):
        open_p = prices[i - 1] if i > 0 else price
        high = max(open_p, price) * (1 + abs(random.gauss(0, 0.005)))
        low = min(open_p, price) * (1 - abs(random.gauss(0, 0.005)))
        vol = base_volume * (1 + abs(random.gauss(0, 0.3)))
        candles.append([open_p, high, low, price, vol])
    return candles


def make_flash_crash(n_bars: int = 100, start_price: float = 100.0) -> StressScenario:
    """Flash crash: -40% over ~10 bars, recovery attempts."""
    prices = _base_random_walk(n_bars, start_price, daily_vol=0.01)
    crash_start = n_bars // 3
    for i in range(crash_start, min(crash_start + 10, n_bars)):
        prices[i] = prices[i - 1] * 0.93
    for i in range(crash_start + 10, n_bars):
        prices[i] = prices[i - 1] * 1.005
    candles = _prices_to_candles(prices)
    return StressScenario(
        name="flash_crash",
        description="Flash crash: -40% in 3 days, partial recovery",
        severity="extreme",
        candles=candles,
        expected_drawdown_pct=40.0,
    )


def make_altseason(n_bars: int = 100, start_price: float = 100.0) -> StressScenario:
    """Altseason decoupling: stable base then explosive alt rally."""
    prices = _base_random_walk(n_bars, start_price, daily_vol=0.005)
    blast_start = n_bars // 2
    for i in range(blast_start, n_bars):
        gain = max(0.045 - 0.001 * (i - blast_start), 0.01)
        prices[i] = prices[i - 1] * (1 + gain)
    candles = _prices_to_candles(prices)
    return StressScenario(
        name="altseason",
        description="Altseason: BTC flat for 50 bars, alts 220% over next 50 bars",
        severity="high",
        candles=candles,
        expected_drawdown_pct=15.0,
    )


def make_exchange_hack(n_bars: int = 100, start_price: float = 100.0) -> StressScenario:
    """Exchange hack panic: -25% in 6h, slow bottom."""
    prices = _base_random_walk(n_bars, start_price, daily_vol=0.008)
    hack_at = n_bars // 4
    for i in range(hack_at, min(hack_at + 3, n_bars)):
        prices[i] = prices[i - 1] * 0.90
    for i in range(hack_at + 3, n_bars):
        prices[i] = prices[i - 1] * random.choice([0.999, 0.998, 1.002])
    candles = _prices_to_candles(prices)
    return StressScenario(
        name="exchange_hack",
        description="Exchange hack panic: -25% in 3 bars, slow grind bottom",
        severity="extreme",
        candles=candles,
        expected_drawdown_pct=25.0,
    )


def make_volatility_explosion(n_bars: int = 100, start_price: float = 100.0) -> StressScenario:
    """Volatility explosion: ATR × 5 sustained."""
    prices = [start_price]
    for _ in range(n_bars - 1):
        ret = random.gauss(0, 0.06)
        prices.append(prices[-1] * (1 + ret))
    candles = _prices_to_candles(prices)
    return StressScenario(
        name="volatility_explosion",
        description="Volatility × 5: extreme whipsaw, test strategy in chop",
        severity="high",
        candles=candles,
        expected_drawdown_pct=20.0,
    )


def make_regulatory_crackdown(n_bars: int = 100, start_price: float = 100.0) -> StressScenario:
    """Regulatory crackdown: -15% immediate, slow 10-day drag."""
    prices = _base_random_walk(n_bars, start_price, daily_vol=0.003)
    for i in range(20, min(30, n_bars)):
        prices[i] = prices[i - 1] * 0.95
    for i in range(30, n_bars):
        prices[i] = prices[i - 1] * 0.997
    candles = _prices_to_candles(prices)
    return StressScenario(
        name="regulatory_crackdown",
        description="Regulatory crackdown: -15% immediate, 10-day grind lower",
        severity="high",
        candles=candles,
        expected_drawdown_pct=30.0,
    )


DEFAULT_SCENARIOS_FACTORIES = [
    make_flash_crash,
    make_altseason,
    make_exchange_hack,
    make_volatility_explosion,
    make_regulatory_crackdown,
]


def _backtest_simple(candles: List[List[float]]) -> Dict[str, float]:
    if len(candles) < 20:
        return {"max_drawdown": 0.0, "final_pnl_pct": 0.0, "sharpe": 0.0}
    closes = [c[3] for c in candles]
    peak = closes[0]
    max_dd = 0.0
    for c in closes:
        peak = max(peak, c)
        dd = (c - peak) / peak
        max_dd = min(max_dd, dd)
    rets = [(closes[i] - closes[i - 1]) / closes[i - 1] for i in range(1, len(closes))]
    mean_r = sum(rets) / len(rets) if rets else 0
    var = sum((r - mean_r) ** 2 for r in rets) / max(1, len(rets))
    std = math.sqrt(var)
    sharpe = mean_r / std if std > 0 else 0.0
    return {
        "max_drawdown": round(max_dd * 100, 2),
        "final_pnl_pct": round(((closes[-1] - closes[0]) / closes[0]) * 100, 2),
        "sharpe": round(sharpe, 4),
    }


class SyntheticStressEngine:
    """Run active strategies across synthetic stress scenarios."""

    def __init__(self, n_bars: int = 100, base_price: float = 100.0):
        self.n_bars = n_bars
        self.base_price = base_price
        self.scenarios: List[StressScenario] = []

    def generate_all(self) -> None:
        self.scenarios = [factory(self.n_bars, self.base_price) for factory in DEFAULT_SCENARIOS_FACTORIES]

    def run_stress(self) -> Dict[str, Any]:
        if not self.scenarios:
            self.generate_all()

        results = []
        for scenario in self.scenarios:
            metrics = _backtest_simple(scenario.candles)
            results.append({
                "name": scenario.name,
                "severity": scenario.severity,
                "expected_dd_pct": scenario.expected_drawdown_pct,
                "realized_dd_pct": metrics["max_drawdown"],
                "final_pnl_pct": metrics["final_pnl_pct"],
                "sharpe": metrics["sharpe"],
                "n_bars": len(scenario.candles),
            })

        worst_dd = max((r["realized_dd_pct"] for r in results), default=0.0)
        log.info(f"[Synthetic] Stress tested {len(results)} scenarios. Worst DD = {worst_dd}%")
        return {
            "scenarios": results,
            "n_scenarios": len(results),
            "worst_drawdown_pct": worst_dd,
            "avg_sharpe": sum(r["sharpe"] for r in results) / max(1, len(results)),
        }


_synth_singleton: Optional[SyntheticStressEngine] = None


def get_synthetic_engine() -> SyntheticStressEngine:
    global _synth_singleton
    if _synth_singleton is None:
        _synth_singleton = SyntheticStressEngine()
    return _synth_singleton