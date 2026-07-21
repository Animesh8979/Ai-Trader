import sys
import math
sys.path.insert(0, 'D:/Ai trader/src')
from godmode.strategies.walk_forward_evaluator import QuantitativeStrategyEvaluator

# Original code but patched
def calculate_metrics_patched(returns, risk_free_rate = 0.05 / 252):
    returns = [r for r in returns if math.isfinite(r)]
    if not returns or len(returns) < 2:
        return {}
    
    n = len(returns)
    total_ret = sum(returns)
    mean_ret = total_ret / n
    excess_returns = [r - risk_free_rate for r in returns]
    mean_excess = sum(excess_returns) / n

    variance = sum((r - mean_ret) ** 2 for r in returns) / (n - 1)
    stdev = max(1e-6, math.sqrt(max(0.0, variance)))

    # Annualized Sharpe (assuming 252 trading days)
    sharpe = (mean_excess / stdev) * math.sqrt(252)

    return sharpe

print(calculate_metrics_patched([0.01 + 1e-16, 0.01 - 1e-16] * 5 + [0.01] * 10))
print(calculate_metrics_patched([0.01, float('nan'), float('inf'), -0.99] * 5))
