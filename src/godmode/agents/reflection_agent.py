"""Reflection Agent for self-calibration based on historical performance.

Queries the SQLite execution database for recent fills and recommends parameter updates
or safety neutral overrides to prevent capital drawdowns.
"""

from __future__ import annotations

from typing import Any, Dict, Optional
from decimal import Decimal
from godmode.core.db import get_db
from godmode.core.logging import get_logger

log = get_logger("agents.reflection_agent")


class ReflectionAgent:
    def __init__(self, check_depth: int = 10):
        self.check_depth = check_depth

    def reflect(self) -> Dict[str, Any]:
        """Query SQLite for the last fills and return performance metrics and recommendations.
        
        Zero-dependency, standard SQL constructs (Ponytail Mindset).
        """
        db = get_db()
        try:
            fills = db.query(
                "SELECT side, realized_pnl FROM fills ORDER BY id DESC LIMIT ?",
                (self.check_depth,)
            )
        except Exception as e:
            log.warning(f"Failed to query fills from DB for reflection: {e}")
            fills = []

        if not fills:
            return {
                "recommended_bias": "no_change",
                "win_rate_pct": 0.0,
                "total_pnl": 0.0,
                "consecutive_losses": 0
            }

        # Calculate metrics
        total_trades = 0
        winning_trades = 0
        total_pnl = Decimal("0.0")
        consecutive_losses = 0
        still_losing = True

        for fill in fills:
            pnl_str = fill.get("realized_pnl") or "0.0"
            pnl_val = Decimal(pnl_str)
            
            # Fills with non-zero PnL are closed trade adjustments
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

        # Calibration Rules:
        # 1. If consecutive losses >= 3, force neutral stance to prevent drawdown spiral
        # 2. If win rate is low (< 35%) and total PnL is negative, recommend neutral stance
        if consecutive_losses >= 3:
            recommended_bias = "neutral"
            reason = f"Conceded {consecutive_losses} consecutive losses. Forcing neutral cooldown."
        elif total_trades >= 3 and win_rate < 35.0 and total_pnl < 0:
            recommended_bias = "neutral"
            reason = f"Win rate is low ({win_rate:.1f}%) and PnL is negative. Restricting bias."
        else:
            recommended_bias = "no_change"
            reason = "Performance metrics within standard tolerances."

        log.info(
            f"Reflection completed: WinRate={win_rate:.1f}%, ConsecutiveLosses={consecutive_losses}, "
            f"TotalPnL={total_pnl} -> RecommendedBias={recommended_bias} (Reason: {reason})"
        )

        return {
            "recommended_bias": recommended_bias,
            "win_rate_pct": float(win_rate),
            "total_pnl": float(total_pnl),
            "consecutive_losses": consecutive_losses,
            "reason": reason
        }
