import sys
import math
sys.path.insert(0, 'D:/Ai trader/src')
from godmode.strategies.walk_forward_evaluator import QuantitativeStrategyEvaluator

# Simulating toxic NaN and Inf from erratic prints
returns = [0.01, float('nan'), float('inf'), -0.99] * 5

evaluator = QuantitativeStrategyEvaluator()
res = evaluator.run_purged_walk_forward(returns)
print(res)
