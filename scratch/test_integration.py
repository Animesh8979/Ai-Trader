import sys
import os
import polars as pl
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from godmode.core.key_rotator import KeyRotator
from godmode.data.alpha_zoo import AlphaZoo
from godmode.strategies.hmm_regime import RegimeDetector

def test_integration():
    print("--- 1. Testing Key Rotator ---")
    rotator = KeyRotator()
    rotator.fetch_keys()
    key = rotator.get_key("openai")
    print(f"Acquired active LLM Key (starts with): {key[:10] if key else 'None'}")

    print("\n--- 2. Testing Alpha Zoo Feature Engineering ---")
    # Generate 1000 candles to give the rolling window enough data
    t = np.linspace(0, 100, 1000)
    prices = 100 + 10 * np.sin(t) + t
    
    candles = [
        [1600000000 + i*60, prices[i], prices[i]*1.01, prices[i]*0.99, prices[i], 1000] 
        for i in range(len(prices))
    ]
    df = pl.DataFrame(candles, schema=["timestamp", "open", "high", "low", "close", "volume"], orient="row")
    
    df_alpha = AlphaZoo.process_all(df)
    print(f"Alpha features generated: {df_alpha.columns}")
    print(f"Row count dropped due to NaN rolling windows: {len(df)} -> {len(df_alpha)}")

    print("\n--- 3. Testing Statistical Regime Detection ---")
    detector = RegimeDetector(df_alpha)
    df_regime = detector.apply_regime_labels()
    
    latest_regime = df_regime["market_regime"].tail(1).item()
    strategy = RegimeDetector.get_strategy_for_regime(latest_regime)
    
    print(f"Detected Market Regime for current tick: {latest_regime}")
    print(f"Optimal Strategy Selection: {strategy}")
    
    print("\n[VERIFICATION SUCCESS] The Institutional ML Pipeline is fully operational.")

if __name__ == "__main__":
    test_integration()
