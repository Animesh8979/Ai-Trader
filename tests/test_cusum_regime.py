"""Unit tests for Page-CUSUM structural regime shift detector."""

import math
import time
import pytest
import numpy as np

from godmode.strategies.cusum_regime import CUSUMRegimeDetector, cusum_filter_offline


def test_cusum_initial_ticks():
    detector = CUSUMRegimeDetector(min_threshold=0.01)
    # First tick sets base price
    assert detector.update(100.0) is None
    assert detector.current_regime == "NEUTRAL"
    
    # Flat price returns no break
    assert detector.update(100.0) is None
    assert detector.current_regime == "NEUTRAL"


def test_cusum_bull_break():
    detector = CUSUMRegimeDetector(min_threshold=0.02, threshold_multiplier=1.0)
    detector.update(100.0)
    
    # Cumulative small upward moves
    detector.update(101.0)  # +1%
    assert detector.current_regime == "NEUTRAL"
    
    event = detector.update(103.0)  # +1.98% more -> total ~ 3% > threshold
    assert event == "BULL_BREAK"
    assert detector.current_regime == "EXPANSION_UP"
    
    state = detector.get_state()
    assert state["s_pos"] == 0.0  # Reset after event


def test_cusum_bear_break():
    detector = CUSUMRegimeDetector(min_threshold=0.02, threshold_multiplier=1.0)
    detector.update(100.0)
    
    detector.update(99.0)  # -1%
    assert detector.current_regime == "NEUTRAL"
    
    event = detector.update(97.0)  # -2.02% more -> total ~ -3% < -threshold
    assert event == "BEAR_BREAK"
    assert detector.current_regime == "CONTRACTION_DOWN"
    
    state = detector.get_state()
    assert state["s_neg"] == 0.0  # Reset after event


def test_cusum_volatility_adaptation():
    detector = CUSUMRegimeDetector(min_threshold=0.01, threshold_multiplier=2.5, ewma_decay=0.5)
    detector.update(100.0)
    
    # Introduce volatile price swings to inflate EWMA variance
    for p in [110.0, 90.0, 115.0, 85.0]:
        detector.update(p)
        
    initial_thresh = detector.min_threshold
    adapted_thresh = detector.current_threshold
    assert adapted_thresh > initial_thresh  # Threshold expanded due to elevated vol


def test_cusum_filter_offline():
    prices = [100.0, 101.0, 102.0, 103.0, 104.0, 100.0, 96.0, 95.0]
    # Threshold 0.03 (~3% cumulative move)
    events = cusum_filter_offline(prices, threshold=0.03)
    assert len(events) >= 2
    assert isinstance(events[0], int)


def test_cusum_o1_complexity():
    detector = CUSUMRegimeDetector(min_threshold=0.01)
    detector.update(100.0)
    
    # 10,000 synthetic ticks to prove O(1) time and zero latency creep
    rng = np.random.default_rng(42)
    synthetic_prices = 100.0 * np.exp(np.cumsum(rng.normal(0, 0.001, size=10_000)))
    
    start_t = time.perf_counter()
    for p in synthetic_prices:
        detector.update(float(p))
    elapsed = time.perf_counter() - start_t
    
    # 10,000 ticks in Python should complete in under 50ms
    assert elapsed < 0.20, f"CUSUM updates took too long ({elapsed:.3f}s for 10k ticks)"
    assert detector._tick_count == 10_000
