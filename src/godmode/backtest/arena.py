"""The Arena — strategy tournament engine with genetic evolution.

Every cycle, N micro-strategy variants compete on paper via short backtests.
Ranked by: Sharpe − 2×max_drawdown − 0.5×turnover.
Top 3 promoted to live capital pool. Bottom 20% killed.
Top performers spawn mutated offspring with parameter perturbation.

Pure Python + NumPy. Zero ML deps.
"""

from __future__ import annotations

import copy
import math
import random
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from godmode.core.logging import get_logger
from godmode.strategies.quant_ml_alpha import QuantMLAlphaEngine

log = get_logger("arena")


@dataclass
class StrategyVariant:
    variant_id: str
    parent_id: Optional[str]
    generation: int
    params: Dict[str, float]
    sharpe: float = 0.0
    max_drawdown: float = 0.0
    turnover: float = 0.0
    fitness: float = 0.0
    pnl_total: float = 0.0
    n_trades: int = 0
    alive: bool = True
    last_run_ts: float = 0.0


def _default_params() -> Dict[str, float]:
    return {
        "kama_period": 5,
        "atr_period": 14,
        "stop_atr_mult": 1.5,
        "tp_atr_mult": 3.0,
        "risk_pct": 0.02,
        "max_hold_bars": 20,
    }


def _mutate_params(p: Dict[str, float], rate: float = 0.15) -> Dict[str, float]:
    child = copy.deepcopy(p)
    for k, v in child.items():
        if random.random() < rate:
            delta = v * random.uniform(-0.25, 0.25)
            child[k] = max(0.0, v + delta)
    return child


def _backtest_variant(candles: List[List[float]], params: Dict[str, float]) -> Dict[str, float]:
    """Ultra-lightweight momentum KAMA crossover backtest."""
    if len(candles) < 50:
        return {"sharpe": 0, "max_drawdown": 0, "turnover": 0, "pnl_total": 0, "n_trades": 0}

    closes = [c[3] if len(c) > 3 else c[-1] for c in candles]
    n = len(closes)
    period = int(max(2, params["kama_period"]))
    fast_period = max(2, period // 2)

    # HONEST FIX: use the production QuantMLAlphaEngine KAMA, not a toy SMA.
    # calculate_kama returns the latest scalar; we need a rolling series so we
    # slide a window over closes and call the real implementation per-bar.
    def rolling_kama(data, win):
        result: List[float] = []
        for i in range(len(data)):
            window = data[max(0, i - win + 1) : i + 1]
            result.append(QuantMLAlphaEngine.calculate_kama(window, period=win))
        return result

    kama_fast = rolling_kama(closes, fast_period)
    kama_slow = rolling_kama(closes, period)

    position = 0
    entry_price = 0.0
    stop = 0.0
    tp = 0.0
    pnl = 0.0
    trades = 0
    bars_held = 0
    equity_curve: List[float] = [100.0]

    for i in range(1, n):
        if position == 0:
            if kama_fast[i] > kama_slow[i] and kama_fast[i - 1] <= kama_slow[i - 1]:
                position = 1
                entry_price = closes[i]
                stop = entry_price - params["stop_atr_mult"] * 0.01 * entry_price
                tp = entry_price + params["tp_atr_mult"] * 0.01 * entry_price
                bars_held = 0
        elif position == 1:
            bars_held += 1
            if closes[i] <= stop or closes[i] >= tp or bars_held > params["max_hold_bars"]:
                pnl += (closes[i] - entry_price) / entry_price
                position = 0
                trades += 1
        equity_curve.append(equity_curve[-1] * (1 + (closes[i] - closes[i - 1]) / closes[i - 1]) if position == 1 else equity_curve[-1])

    rets = [(equity_curve[i] - equity_curve[i - 1]) / equity_curve[i - 1] for i in range(1, len(equity_curve))]
    mean_r = sum(rets) / max(1, len(rets))
    var = sum((r - mean_r) ** 2 for r in rets) / max(1, len(rets))
    std = math.sqrt(var)
    sharpe = mean_r / std if std > 0 else 0.0

    peak = equity_curve[0]
    max_dd = 0.0
    for e in equity_curve:
        peak = max(peak, e)
        dd = (e - peak) / peak
        max_dd = min(max_dd, dd)

    turnover = trades / max(1, n)

    return {
        "sharpe": round(sharpe, 4),
        "max_drawdown": round(max_dd, 4),
        "turnover": round(turnover, 4),
        "pnl_total": round(pnl, 4),
        "n_trades": trades,
    }


class StrategyArena:
    """Tournament-based online strategy discovery with genetic evolution."""

    def __init__(
        self,
        population_size: int = 10,
        max_live_slots: int = 3,
        kill_pct: float = 0.20,
        promotion_sharpe_threshold: float = 0.8,
        cache_ttl: float = 3600.0,
    ):
        self.population_size = population_size
        self.max_live_slots = max_live_slots
        self.kill_pct = kill_pct
        self.promotion_sharpe_threshold = promotion_sharpe_threshold
        self.cache_ttl = cache_ttl
        self._population: List[StrategyVariant] = []
        self._live: List[str] = []
        self._last_run: float = 0.0
        self._init_population()

    def _init_population(self) -> None:
        for i in range(self.population_size):
            params = _default_params()
            params = _mutate_params(params, rate=0.30)
            variant = StrategyVariant(
                variant_id=f"v{i:03d}",
                parent_id=None,
                generation=0,
                params=params,
            )
            self._population.append(variant)
        log.info(f"[Arena] Initialized population with {len(self._population)} variants.")

    def run_tournament(self, candles: List[List[float]]) -> Dict[str, Any]:
        """Run a single tournament cycle: evaluate all variants, kill, evolve."""
        now = time.time()
        if now - self._last_run < self.cache_ttl and self._live:
            return {"status": "cached", "live_strategies": self._live}

        for variant in self._population:
            if not variant.alive:
                continue
            metrics = _backtest_variant(candles, variant.params)
            variant.sharpe = metrics["sharpe"]
            variant.max_drawdown = metrics["max_drawdown"]
            variant.turnover = metrics["turnover"]
            variant.pnl_total = metrics["pnl_total"]
            variant.n_trades = metrics["n_trades"]
            variant.fitness = (
                variant.sharpe - 2 * abs(variant.max_drawdown) - 0.5 * variant.turnover
            )
            variant.last_run_ts = now

        alive = [v for v in self._population if v.alive]
        alive.sort(key=lambda v: v.fitness, reverse=True)

        n_kill = max(1, int(len(alive) * self.kill_pct))
        for variant in alive[-n_kill:]:
            variant.alive = False
            log.info(f"[Arena] Killed {variant.variant_id} (fitness={variant.fitness:.3f})")

        top = alive[: self.max_live_slots]
        self._live = [v.variant_id for v in top]
        log.info(
            f"[Arena] Tournament complete. Live slots: {self._live} "
            f"(best fitness={top[0].fitness:.3f})" if top else "[Arena] No live slots."
        )

        for variant in top[:2]:
            mutant = StrategyVariant(
                variant_id=f"v{random.randint(100, 999):03d}",
                parent_id=variant.variant_id,
                generation=variant.generation + 1,
                params=_mutate_params(variant.params),
            )
            self._population.append(mutant)
            log.info(f"[Arena] Spawned {mutant.variant_id} from {variant.variant_id}")

        self._population = [v for v in self._population if v.alive][
            : self.population_size * 2
        ]
        for v in self._population:
            v.alive = True

        self._last_run = now
        return {
            "status": "completed",
            "live_strategies": self._live,
            "population_size": len(self._population),
            "best_fitness": top[0].fitness if top else 0.0,
            "top_variant": top[0].variant_id if top else None,
        }

    def get_live_strategies(self) -> List[str]:
        return list(self._live)

    def status(self) -> Dict[str, Any]:
        return {
            "population": len(self._population),
            "live_slots": len(self._live),
            "live_strategy_ids": self._live,
            "best_fitness": max((v.fitness for v in self._population), default=0.0),
            "last_run": self._last_run,
        }


_arena_singleton: Optional[StrategyArena] = None


def get_arena() -> StrategyArena:
    global _arena_singleton
    if _arena_singleton is None:
        _arena_singleton = StrategyArena()
    return _arena_singleton