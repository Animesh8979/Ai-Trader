"""Page-CUSUM (Cumulative Sum) Structural Regime Shift Detector.

Grounded in:
- Page, E. S. (1954). "Continuous Inspection Schemes." Biometrika, 41(1/2), 100-115.
- Lopez de Prado, M. (2018). "Advances in Financial Machine Learning", Ch. 2.5 (The CUSUM Filter).

Provides an O(1) constant-time, constant-space alternative to Bayesian Online Changepoint
Detection (BOCPD), eliminating quadratic O(t^2) computation, memory accumulation, and regime chatter
on non-i.i.d. financial tick data.
"""

from __future__ import annotations

import math
from typing import List, Optional, Tuple, Union
import numpy as np


class CUSUMRegimeDetector:
    """Online, constant-time O(1) symmetric two-sided CUSUM filter.
    
    Tracks cumulative positive and negative deviations from expected return.
    When cumulative deviation exceeds threshold h = multiplier * sigma,
    a structural break event is triggered and the corresponding accumulator resets.
    """

    def __init__(
        self,
        threshold_multiplier: float = 2.5,
        min_threshold: float = 0.002,  # 20 bps minimum return break
        ewma_decay: float = 0.94,      # RiskMetrics EWMA volatility decay
    ):
        self.multiplier = float(threshold_multiplier)
        self.min_threshold = float(min_threshold)
        self.ewma_decay = float(ewma_decay)

        self._last_price: Optional[float] = None
        self._s_pos: float = 0.0
        self._s_neg: float = 0.0
        self._ewma_variance: float = (min_threshold / max(1.0, threshold_multiplier)) ** 2
        self._current_regime: str = "NEUTRAL"
        self._tick_count: int = 0

    @property
    def current_regime(self) -> str:
        return self._current_regime

    @property
    def current_volatility(self) -> float:
        return math.sqrt(max(1e-8, self._ewma_variance))

    @property
    def current_threshold(self) -> float:
        return max(self.min_threshold, self.multiplier * self.current_volatility)

    def update(self, price: float) -> Optional[str]:
        """Processes a new tick or candle close price in O(1) time.
        
        Returns:
            "BULL_BREAK" if upward structural break detected,
            "BEAR_BREAK" if downward structural break detected,
            None otherwise.
        """
        p = float(price)
        if p <= 0:
            return None

        if self._last_price is None:
            self._last_price = p
            return None

        # Continuous compounding return: ln(p_t / p_{t-1})
        ret = math.log(p / self._last_price)
        self._last_price = p
        self._tick_count += 1

        # Online EWMA variance update
        decay = self.ewma_decay
        self._ewma_variance = decay * self._ewma_variance + (1.0 - decay) * (ret ** 2)

        # Dynamic volatility threshold
        h = self.current_threshold

        # Update two-sided CUSUM statistics
        self._s_pos = max(0.0, self._s_pos + ret)
        self._s_neg = min(0.0, self._s_neg + ret)

        event: Optional[str] = None

        if self._s_pos >= h:
            event = "BULL_BREAK"
            self._current_regime = "EXPANSION_UP"
            self._s_pos = 0.0
        elif self._s_neg <= -h:
            event = "BEAR_BREAK"
            self._current_regime = "CONTRACTION_DOWN"
            self._s_neg = 0.0

        return event

    def reset(self) -> None:
        """Resets accumulators while keeping learned volatility parameter."""
        self._s_pos = 0.0
        self._s_neg = 0.0
        self._last_price = None
        self._current_regime = "NEUTRAL"

    def get_state(self) -> dict:
        return {
            "s_pos": self._s_pos,
            "s_neg": self._s_neg,
            "threshold": self.current_threshold,
            "volatility": self.current_volatility,
            "regime": self._current_regime,
            "tick_count": self._tick_count,
        }


def cusum_filter_offline(
    prices: Union[List[float], np.ndarray],
    threshold: float
) -> List[int]:
    """Batch Lopez de Prado CUSUM filter over historical price series.
    
    Returns:
        List of integer indices where structural break events occurred.
    """
    arr = np.asarray(prices, dtype=np.float64)
    if len(arr) < 2:
        return []

    events: List[int] = []
    s_pos = 0.0
    s_neg = 0.0

    # Calculate log returns
    log_returns = np.diff(np.log(arr))

    for i, ret in enumerate(log_returns, start=1):
        s_pos = max(0.0, s_pos + ret)
        s_neg = min(0.0, s_neg + ret)

        if s_pos >= threshold:
            events.append(i)
            s_pos = 0.0
        elif s_neg <= -threshold:
            events.append(i)
            s_neg = 0.0

    return events
