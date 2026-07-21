"""Reflection v2 — Self-calibration with dynamic brain injection.

Queries SQLite for recent fills, computes win rate / consecutive losses /
drawdown-based bias overrides, and generates a reflection summary string
that gets injected into the Macro Council prompt.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, Optional

from godmode.core.db import get_db
from godmode.core.logging import get_logger

log = get_logger("agents.reflection_v2")


@dataclass
class ReflectionInsight:
    recommended_bias: str
    win_rate_pct: float
    total_pnl: float
    consecutive_losses: int
    bull_weight_adjustment: float
    bear_weight_adjustment: float
    reason: str
    insight_block: str


class ReflectionAgentV2:
    """V2: dynamic prompt injection + Bull/Bear weight calibration."""

    def __init__(self, check_depth: int = 10):
        self.check_depth = check_depth

    def reflect(self) -> ReflectionInsight:
        db = get_db()
        fills = []
        try:
            fills = db.query(
                "SELECT side, realized_pnl FROM fills ORDER BY id DESC LIMIT ?",
                (self.check_depth,),
            )
        except Exception as e:
            log.warning(f"Reflection DB query failed: {e}")

        if not fills:
            return self._default_insight()

        total_trades = 0
        winning_trades = 0
        total_pnl = Decimal("0.0")
        consecutive_losses = 0
        still_losing = True

        for fill in fills:
            pnl_val = Decimal(str(fill.get("realized_pnl") or "0.0"))
            if pnl_val != Decimal("0.0"):
                total_trades += 1
                total_pnl += pnl_val
                if pnl_val > 0:
                    winning_trades += 1
                    still_losing = False
                else:
                    if still_losing:
                        consecutive_losses += 1

        win_rate = (winning_trades / total_trades * 100.0) if total_trades > 0 else 50.0

        if consecutive_losses >= 3:
            bias = "neutral"
            bull_adj = -0.3
            bear_adj = -0.3
            reason = f"Forced neutral: {consecutive_losses} consecutive losses."
        elif total_trades >= 3 and win_rate < 35.0 and total_pnl < 0:
            bias = "neutral"
            bull_adj = -0.2
            bear_adj = +0.2
            reason = f"Win rate {win_rate:.1f}% too low, PnL negative. Defensive bias."
        elif win_rate > 65.0 and total_pnl > 0:
            bias = "no_change"
            bull_adj = +0.1
            bear_adj = -0.1
            reason = f"Strong run ({win_rate:.1f}% win rate). Slight bull tilt."
        else:
            bias = "no_change"
            bull_adj = 0.0
            bear_adj = 0.0
            reason = "Performance within tolerance."

        insight_block = (
            f"[Reflection v2]\n"
            f"- Last {self.check_depth} fills: {win_rate:.1f}% win rate, "
            f"PnL={total_pnl}, consec losses={consecutive_losses}\n"
            f"- Recommended bias: {bias}\n"
            f"- Bull weight adj: {bull_adj:+.2f}, Bear weight adj: {bear_adj:+.2f}\n"
            f"- Reason: {reason}"
        )

        log.info(f"Reflection v2: {reason}")
        return ReflectionInsight(
            recommended_bias=bias,
            win_rate_pct=float(win_rate),
            total_pnl=float(total_pnl),
            consecutive_losses=consecutive_losses,
            bull_weight_adjustment=bull_adj,
            bear_weight_adjustment=bear_adj,
            reason=reason,
            insight_block=insight_block,
        )

    @staticmethod
    def _default_insight() -> ReflectionInsight:
        return ReflectionInsight(
            recommended_bias="no_change",
            win_rate_pct=0.0,
            total_pnl=0.0,
            consecutive_losses=0,
            bull_weight_adjustment=0.0,
            bear_weight_adjustment=0.0,
            reason="No historical fills yet.",
            insight_block="[Reflection v2] No historical fills yet. Defaulting to neutral.",
        )


_reflection_singleton: Optional[ReflectionAgentV2] = None


def get_reflection() -> ReflectionAgentV2:
    global _reflection_singleton
    if _reflection_singleton is None:
        _reflection_singleton = ReflectionAgentV2()
    return _reflection_singleton