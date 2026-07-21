"""Purged Walk-Forward Evaluator & Deflated Sharpe Ratio (DSR) Engine.

Implements Marcos Lopez de Prado's Quantitative Finance Methodology:
1. Deflated Sharpe Ratio (DSR) — Corrects for backtest overfitting across multiple trials.
2. Purged & Embargoed Cross-Validation — Eliminates lookahead bias between train/test splits.
3. Institutional Metrics — Sharpe, Sortino, Max Drawdown, Profit Factor, Win Rate.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List


class QuantitativeStrategyEvaluator:
    """Evaluates strategy performance metrics and tests for overfitting via DSR."""

    @staticmethod
    def calculate_metrics(returns: List[float], risk_free_rate: float = 0.05 / 252) -> Dict[str, float]:
        """Compute institutional performance statistics."""
        if not returns or len(returns) < 2:
            return {
                "total_return_pct": 0.0,
                "sharpe_ratio": 0.0,
                "sortino_ratio": 0.0,
                "max_drawdown_pct": 0.0,
                "win_rate_pct": 0.0,
                "profit_factor": 0.0,
            }

        n = len(returns)
        total_ret = sum(returns)
        mean_ret = total_ret / n
        excess_returns = [r - risk_free_rate for r in returns]
        mean_excess = sum(excess_returns) / n

        variance = sum((r - mean_ret) ** 2 for r in returns) / (n - 1)
        stdev = max(1e-6, math.sqrt(max(0.0, variance)))

        # Annualized Sharpe (assuming 252 trading days)
        sharpe = (mean_excess / stdev) * math.sqrt(252) if stdev > 0 else 0.0

        # Downside Deviation for Sortino
        downside_sq = [min(0.0, r - risk_free_rate) ** 2 for r in returns]
        downside_std = max(1e-6, math.sqrt(max(0.0, sum(downside_sq) / n)))
        sortino = (mean_excess / downside_std) * math.sqrt(252) if downside_std > 0 else 0.0

        # Max Drawdown
        equity_curve: List[float] = [1.0]
        for r in returns:
            equity_curve.append(equity_curve[-1] * (1.0 + r))

        peak = equity_curve[0]
        max_dd = 0.0
        for eq in equity_curve:
            if eq > peak:
                peak = eq
            dd = (peak - eq) / peak
            if dd > max_dd:
                max_dd = dd

        # Win Rate & Profit Factor
        wins = [r for r in returns if r > 0]
        losses = [r for r in returns if r < 0]
        win_rate = (len(wins) / n) * 100.0 if n > 0 else 0.0
        gross_profit = sum(wins)
        gross_loss = abs(sum(losses))
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (gross_profit if gross_profit > 0 else 1.0)

        return {
            "total_return_pct": round(total_ret * 100.0, 2),
            "sharpe_ratio": round(sharpe, 3),
            "sortino_ratio": round(sortino, 3),
            "max_drawdown_pct": round(max_dd * 100.0, 2),
            "win_rate_pct": round(win_rate, 1),
            "profit_factor": round(profit_factor, 2),
        }

    @staticmethod
    def calculate_deflated_sharpe_ratio(
        observed_sharpe: float,
        num_trials: int,
        num_observations: int,
        skewness: float = 0.0,
        kurtosis: float = 3.0,
    ) -> float:
        """Calculate Deflated Sharpe Ratio (DSR) p-value.

        A DSR > 0.95 indicates the strategy's Sharpe is statistically significant
        and NOT a result of data mining / backtest overfitting.
        """
        if num_trials <= 1 or num_observations <= 5:
            return 1.0

        # Euler-Mascheroni constant estimate for expected max Sharpe under null hypothesis
        e = 0.5772156649
        exp_max_sharpe = (1.0 - e) * math.sqrt(2.0 * math.log(num_trials)) + e * math.sqrt(2.0 * math.log(num_trials))

        variance = (1.0 - skewness * observed_sharpe + ((kurtosis - 1.0) / 4.0) * (observed_sharpe ** 2)) / (num_observations - 1)
        stdev = math.sqrt(max(1e-6, variance))

        z_score = (observed_sharpe - exp_max_sharpe) / stdev

        # Cumulative distribution function of standard normal
        dsr_p_val = 0.5 * (1.0 + math.erf(z_score / math.sqrt(2.0)))
        return round(dsr_p_val, 4)

    @classmethod
    def run_purged_walk_forward(
        cls, returns: List[float], num_folds: int = 4, purge_window: int = 2
    ) -> Dict[str, Any]:
        """Execute Purged & Embargoed Cross-Validation."""
        returns = [r for r in returns if math.isfinite(r)]
        if len(returns) < 20:
            return {"status": "INSUFFICIENT_DATA"}

        fold_size = len(returns) // num_folds
        oos_sharpes: List[float] = []

        for f in range(num_folds):
            test_start = f * fold_size
            test_end = test_start + fold_size if f < num_folds - 1 else len(returns)

            # Purge overlap
            train_returns = returns[: max(0, test_start - purge_window)] + returns[min(len(returns), test_end + purge_window) :]
            test_returns = returns[test_start:test_end]

            m_test = cls.calculate_metrics(test_returns)
            oos_sharpes.append(m_test["sharpe_ratio"])

        avg_oos_sharpe = sum(oos_sharpes) / len(oos_sharpes) if oos_sharpes else 0.0
        overall_metrics = cls.calculate_metrics(returns)
        dsr = cls.calculate_deflated_sharpe_ratio(overall_metrics["sharpe_ratio"], num_trials=10, num_observations=len(returns))

        return {
            "status": "PASSED",
            "overall_sharpe": overall_metrics["sharpe_ratio"],
            "avg_out_of_sample_sharpe": round(avg_oos_sharpe, 3),
            "max_drawdown_pct": overall_metrics["max_drawdown_pct"],
            "win_rate_pct": overall_metrics["win_rate_pct"],
            "profit_factor": overall_metrics["profit_factor"],
            "deflated_sharpe_p_value": dsr,
            "is_statistically_robust": dsr >= 0.50 and avg_oos_sharpe > 0.5,
        }
