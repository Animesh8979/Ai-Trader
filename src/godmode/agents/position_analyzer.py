"""PositionAnalyzer Agent — S/R zones, pivot points, VWAP, range positioning.

Feeds Bull/Bear debate with contextual technical analysis:
 - Current price position within range (0-100%)
 - Pivot point levels (S2, S1, PP, R1, R2)
 - VWAP distance
 - Key support/resistance zone proximity
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class PositionContext:
    symbol: str
    price: float
    range_pct: float
    nearest_level: str  # "support", "resistance", "mid"
    distance_to_level_pct: float
    pivot_points: Dict[str, float]
    vwap_distance_pct: float
    summary: str


class PositionAnalyzer:
    """Pure Python position analysis — no libraries needed."""

    @classmethod
    def calculate_pivots(cls, high: float, low: float, close: float) -> Dict[str, float]:
        pp = (high + low + close) / 3
        return {
            "R3": pp + 2 * (high - low),
            "R2": pp + (high - low),
            "R1": 2 * pp - low,
            "PP": pp,
            "S1": 2 * pp - high,
            "S2": pp - (high - low),
            "S3": pp - 2 * (high - low),
        }

    @classmethod
    def calculate_vwap(cls, candles: List[List[float]]) -> float:
        """candles: [open, high, low, close, volume]"""
        total_pv = 0.0
        total_vol = 0.0
        for c in candles:
            typical = (c[1] + c[2] + c[3]) / 3.0
            total_pv += typical * max(c[4], 0)
            total_vol += max(c[4], 0)
        return total_pv / total_vol if total_vol > 0 else candles[-1][3]

    @classmethod
    def analyze(cls, symbol: str, candles: List[List[float]]) -> PositionContext:
        """
        candles: List of [open, high, low, close, volume], last element is current.
        """
        if len(candles) < 5:
            return PositionContext(
                symbol=symbol,
                price=0.0,
                range_pct=0.0,
                nearest_level="unknown",
                distance_to_level_pct=0.0,
                pivot_points={},
                vwap_distance_pct=0.0,
                summary="Insufficient data",
            )

        current = candles[-1]
        price = current[3]
        recent_high = max(c[1] for c in candles[-20:])
        recent_low = min(c[2] for c in candles[-20:])

        range_size = recent_high - recent_low
        if range_size == 0:
            range_pct = 50.0
        else:
            range_pct = ((price - recent_low) / range_size) * 100.0
            range_pct = max(0.0, min(100.0, range_pct))

        pivots = cls.calculate_pivots(recent_high, recent_low, price)
        vwap = cls.calculate_vwap(candles[-20:])
        vwap_dist = ((price - vwap) / vwap * 100.0) if vwap > 0 else 0.0

        levels = []
        for name, level in pivots.items():
            diff_pct = abs(price - level) / price * 100
            levels.append((name, level, diff_pct))

        nearest = min(levels, key=lambda x: x[2])

        side = "support" if nearest[1] <= price else "resistance"

        return PositionContext(
            symbol=symbol,
            price=price,
            range_pct=round(range_pct, 1),
            nearest_level=side,
            distance_to_level_pct=round(nearest[2], 2),
            pivot_points={k: round(v, 2) for k, v in pivots.items()},
            vwap_distance_pct=round(vwap_dist, 2),
            summary=(
                f"Price at {range_pct:.1f}% of range, "
                f"{vwap_dist:+.2f}% from VWAP, "
                f"{nearest[2]:.2f}% from nearest {side} ({nearest[0]}={nearest[1]:.2f})"
            ),
        )