---
name: "Backtest Metrics Reporting"
description: "Compiles, parses, and formats NautilusTrader backtest results."
---
# Backtest Metrics Reporting Skill

This skill governs the parsing and compiling of backtest logs, Sharpe/Sortino ratios, and execution stats.

## Core Metrics
- **Sharpe Ratio**: Annualized return divided by annualized volatility.
- **Sortino Ratio**: Annualized return divided by downside deviation.
- **Win Rate**: Ratio of winning fills to total executed fills.
- **Max Drawdown**: Peak-to-trough decline percentage during the backtest window.
