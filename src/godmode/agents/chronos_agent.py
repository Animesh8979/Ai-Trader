"""Chronos Prophet Agent.

Provides zero-shot style time-series forecasts and probabilistic price target distributions 
using historical volatility and drift projections.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional
from godmode.core.logging import get_logger

log = get_logger("agents.chronos_agent")


class ChronosProphetAgent:
    def __init__(self, forecast_steps: int = 5):
        self.forecast_steps = forecast_steps

    def predict_distribution(self, prices: List[float]) -> Dict[str, float]:
        """Calculate probabilistic price distribution targets (P10, P50, P90).
        
        Uses Geometric Brownian Motion (GBM) drift and volatility calculations.
        Safe for local CPU (zero-dependency, YAGNI, standard library first).
        """
        if len(prices) < 5:
            log.warning("Insufficient prices for distribution prediction. Returning defaults.")
            last_price = prices[-1] if prices else 0.0
            return {"p10": last_price, "p50": last_price, "p90": last_price}

        last_price = prices[-1]

        # 1. Calculate log returns
        log_returns = []
        for i in range(1, len(prices)):
            if prices[i-1] > 0 and prices[i] > 0:
                log_returns.append(math.log(prices[i] / prices[i-1]))

        if not log_returns:
            return {"p10": last_price, "p50": last_price, "p90": last_price}

        # 2. Compute drift (mean return) and variance
        n = len(log_returns)
        mean_return = sum(log_returns) / n
        variance = sum((r - mean_return) ** 2 for r in log_returns) / max(1, n - 1)
        volatility = math.sqrt(variance)

        # 3. Project P50 (median), P90 (optimistic), P10 (conservative) price targets
        # standard normal z-scores: P90 (z = 1.28), P10 (z = -1.28)
        t = self.forecast_steps
        drift_adjustment = mean_return * t
        vol_adjustment = volatility * math.sqrt(t)

        p50 = last_price * math.exp(drift_adjustment)
        p90 = last_price * math.exp(drift_adjustment + 1.28 * vol_adjustment)
        p10 = last_price * math.exp(drift_adjustment - 1.28 * vol_adjustment)

        log.info(
            f"Chronos Prophet: Closes={len(prices)}, Last={last_price:.2f} -> "
            f"P10={p10:.2f}, P50={p50:.2f}, P90={p90:.2f}"
        )

        return {
            "p10": round(p10, 4),
            "p50": round(p50, 4),
            "p90": round(p90, 4)
        }
