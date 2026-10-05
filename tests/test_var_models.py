"""Unit tests for quantitative VaR and Expected Shortfall models."""

from __future__ import annotations

import math
import numpy as np
import pytest

from godmode.risk.var_models import (
    calculate_moments,
    normal_quantile,
    cornish_fisher_quantile,
    cornish_fisher_var,
    filtered_historical_simulation_var,
)


def test_normal_quantile_accuracy():
    """Verify Acklam/Abramowitz rational approximation matches known statistical tables."""
    assert math.isclose(normal_quantile(0.5), 0.0, abs_tol=1e-4)
    assert math.isclose(normal_quantile(0.975), 1.95996, abs_tol=1e-3)
    assert math.isclose(normal_quantile(0.025), -1.95996, abs_tol=1e-3)
    assert math.isclose(normal_quantile(0.01), -2.3263, abs_tol=1e-3)
    assert math.isclose(normal_quantile(0.001), -3.0902, abs_tol=1e-2)


def test_calculate_moments():
    """Test sample moments on known standard normal distribution."""
    np.random.seed(42)
    sample = np.random.normal(0.0, 1.0, 5000)
    mean, var, skew, kurt = calculate_moments(sample)
    
    assert math.isclose(mean, 0.0, abs_tol=0.05)
    assert math.isclose(var, 1.0, abs_tol=0.08)
    assert math.isclose(skew, 0.0, abs_tol=0.10)
    assert math.isclose(kurt, 0.0, abs_tol=0.20)


def test_cornish_fisher_monotonicity_guard():
    """Verify that extreme skewness/kurtosis falls back safely without quantile inversion."""
    # Under extreme negative skew, raw CF polynomial would invert or produce negative risk
    cf_z_normal = cornish_fisher_quantile(0.01, skew=0.0, excess_kurt=0.0)
    assert cf_z_normal < -2.0

    # Extreme skew: should be caught by monotonicity domain check
    cf_z_extreme = cornish_fisher_quantile(0.01, skew=-3.0, excess_kurt=10.0)
    assert cf_z_extreme <= normal_quantile(0.01)  # Stays conservative and monotonic


def test_cornish_fisher_var_calculation():
    """Verify CF-VaR outputs positive realistic percentage loss."""
    np.random.seed(42)
    # 100 days of returns with negative tail
    returns = np.random.normal(0.0005, 0.02, 200)
    returns[10] = -0.08  # Flash crash tail event
    
    var_99 = cornish_fisher_var(returns, confidence_level=0.99)
    assert 0.02 < var_99 < 0.15  # VaR between 2% and 15%
    assert var_99 > 0.0  # Must be strictly positive loss


def test_filtered_historical_simulation_var():
    """Verify Hull-White FHS adapts to volatility and CVaR >= VaR."""
    np.random.seed(42)
    returns = np.random.normal(0.0002, 0.015, 300)
    returns[50] = -0.06
    
    # In low volatility regime
    var_low, cvar_low = filtered_historical_simulation_var(returns, current_volatility=0.01, confidence_level=0.99)
    # In high volatility regime
    var_high, cvar_high = filtered_historical_simulation_var(returns, current_volatility=0.04, confidence_level=0.99)
    
    assert cvar_low >= var_low
    assert cvar_high >= var_high
    assert var_high > var_low  # Scaled by current market volatility
