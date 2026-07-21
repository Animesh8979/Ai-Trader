"""Quantitative ML Alpha Engine — KAMA, Supertrend, & Markov Regime Classification.

Provides zero-dependency CPU-optimized indicators & regime classification matrices.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List


class QuantMLAlphaEngine:
    """Computes advanced quant indicators and Markov state probabilities."""

    @staticmethod
    def calculate_kama(closes: List[float], period: int = 10, fast_span: int = 2, slow_span: int = 30) -> float:
        """Calculate Kaufman Adaptive Moving Average (KAMA)."""
        if len(closes) <= period:
            return closes[-1] if closes else 0.0

        direction = abs(closes[-1] - closes[-1 - period])
        volatility = sum(abs(closes[i] - closes[i - 1]) for i in range(len(closes) - period, len(closes)))
        er = direction / volatility if volatility != 0 else 0.0

        fast_sc = 2.0 / (fast_span + 1)
        slow_sc = 2.0 / (slow_span + 1)
        sc = (er * (fast_sc - slow_sc) + slow_sc) ** 2

        kama = closes[-1 - period]
        for c in closes[-period:]:
            kama = kama + sc * (c - kama)
        return round(kama, 4)

    @staticmethod
    def calculate_supertrend(highs: List[float], lows: List[float], closes: List[float], period: int = 10, multiplier: float = 3.0) -> Dict[str, Any]:
        """Calculate Supertrend direction and trailing stop value."""
        if len(closes) < period:
            return {"supertrend": closes[-1] if closes else 0.0, "direction": "UP"}

        # Calculate ATR
        tr_list: List[float] = []
        for i in range(1, len(closes)):
            hl = highs[i] - lows[i]
            hc = abs(highs[i] - closes[i - 1])
            lc = abs(lows[i] - closes[i - 1])
            tr_list.append(max(hl, hc, lc))

        atr = sum(tr_list[-period:]) / period if tr_list else 1.0

        hl2 = (highs[-1] + lows[-1]) / 2.0
        upper_band = hl2 + multiplier * atr
        lower_band = hl2 - multiplier * atr

        direction = "UP" if closes[-1] > upper_band else ("DOWN" if closes[-1] < lower_band else "UP")
        stop_val = lower_band if direction == "UP" else upper_band

        return {
            "supertrend": round(stop_val, 4),
            "direction": direction,
            "atr": round(atr, 4),
        }

    @staticmethod
    def classify_markov_regime(returns: List[float]) -> Dict[str, float]:
        """Classify current market regime (Bullish, Bearish, Range) via transition probabilities."""
        if not returns or len(returns) < 5:
            return {"bull_prob": 0.33, "bear_prob": 0.33, "range_prob": 0.34}

        pos_count = sum(1 for r in returns if r > 0.001)
        neg_count = sum(1 for r in returns if r < -0.001)
        neutral_count = len(returns) - pos_count - neg_count
        total = len(returns)

        return {
            "bull_prob": round(pos_count / total, 3),
            "bear_prob": round(neg_count / total, 3),
            "range_prob": round(neutral_count / total, 3),
        }
