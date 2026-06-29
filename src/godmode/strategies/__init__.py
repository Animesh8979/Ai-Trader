"""Deterministic quant strategies (Phase 1).

Baseline, fully-deterministic strategies (e.g. momentum, mean-reversion) that form the
substrate the LLM brain advises on. Same code path across backtest / paper / live.
"""

from godmode.strategies.risk_guarded_strategy import RiskGuardedStrategy
from godmode.strategies.ema_crossover import EMACrossover, EMACrossoverConfig

__all__ = ["RiskGuardedStrategy", "EMACrossover", "EMACrossoverConfig"]

