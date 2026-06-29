"""Backtest harness, metrics, and reports (Phase 1).

Runs strategies over historical data with no look-ahead bias and a walk-forward /
out-of-sample split to surface overfitting. Emits a readable report (Sharpe, Sortino,
max drawdown, win rate, profit factor, exposure).
"""

from godmode.backtest.runner import run_backtest

__all__ = ["run_backtest"]

