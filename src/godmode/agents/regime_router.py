"""RegimeRouter Agent — TDDR + ADX + Volatility regime classifier.

Replaces the flat 5-step pipeline in brain.py with a dynamic routing dispatcher.
Classifies market state into: TRENDING_UP, TRENDING_DOWN, CHOPPY, RANGING.
Routes to different strategy templates based on regime.
Uses pure Polars + NumPy — zero heavy ML deps.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, Dict, List, Optional


class Regime(Enum):
    TRENDING_UP = auto()
    TRENDING_DOWN = auto()
    CHOPPY = auto()
    RANGING = auto()
    UNKNOWN = auto()


@dataclass
class RegimeSignal:
    regime: Regime
    confidence: float
    strategy: str
    details: Dict[str, float]


class RegimeRouter:
    """Pure Python regime classifier using ADX/ATR/volume spread analysis."""

    @staticmethod
    def _rolling_mean(data: List[float], window: int) -> List[float]:
        result = []
        for i in range(len(data)):
            start = max(0, i - window + 1)
            result.append(sum(data[start : i + 1]) / (i - start + 1))
        return result

    @staticmethod
    def _tr(high: float, low: float, prev_close: float) -> float:
        return max(high - low, abs(high - prev_close), abs(low - prev_close))

    @staticmethod
    def _hurst_exponent(series: List[float], min_lag: int = 2, max_lag: int = 20) -> float:
        """Estimate Hurst exponent via Rescaled-Range (R/S) analysis.

        Hurst > 0.5  -> persistent (trending)
        Hurst < 0.5  -> anti-persistent (mean-reverting)
        Hurst ~ 0.5  -> random walk

        Pure Python, no scipy/numpy. Returns 0.5 if insufficient data.
        Reference: Hurst, H.E. (1951). "Long-term storage capacity of reservoirs."
        """
        n = len(series)
        if n < max_lag * 2:
            return 0.5

        # Use log-returns for price series (works for any positive series).
        if all(x > 0 for x in series[:max(3, n // 10)]):
            ts = [math.log(series[i] / series[i - 1])
                  for i in range(1, n) if series[i - 1] > 0 and series[i] > 0]
        else:
            ts = series.copy()
        if len(ts) < max_lag * 2:
            return 0.5

        lags = list(range(min_lag, min(max_lag, len(ts) // 2) + 1))
        rs_values = []
        for lag in lags:
            # Slice into non-overlapping windows of length `lag`.
            n_chunks = len(ts) // lag
            if n_chunks < 1:
                continue
            chunk_rs = []
            for c in range(n_chunks):
                chunk = ts[c * lag : (c + 1) * lag]
                if len(chunk) < 2:
                    continue
                mean = sum(chunk) / len(chunk)
                deviations = [x - mean for x in chunk]
                cumdev = 0.0
                cumdev_series = []
                for d in deviations:
                    cumdev += d
                    cumdev_series.append(cumdev)
                if not cumdev_series:
                    continue
                r_val = max(cumdev_series) - min(cumdev_series)
                s_val = (sum(d * d for d in deviations) / len(deviations)) ** 0.5
                if s_val > 0:
                    chunk_rs.append(r_val / s_val)
            if chunk_rs:
                rs_values.append((math.log(lag), math.log(sum(chunk_rs) / len(chunk_rs))))

        if len(rs_values) < 3:
            return 0.5

        # Linear regression: log(R/S) = H * log(lag) + c
        # Slope of regression = Hurst exponent.
        xs = [p[0] for p in rs_values]
        ys = [p[1] for p in rs_values]
        n_pts = len(xs)
        x_mean = sum(xs) / n_pts
        y_mean = sum(ys) / n_pts
        num = sum((xs[i] - x_mean) * (ys[i] - y_mean) for i in range(n_pts))
        den = sum((xs[i] - x_mean) ** 2 for i in range(n_pts))
        if den == 0:
            return 0.5
        h = num / den
        # Clamp to a sane physical range.
        return max(0.0, min(1.0, h))

    @staticmethod
    def _higuchi_fractal_dimension(series: List[float], k_max: int = 8) -> float:
        """Estimate the fractal dimension D of a series via Higuchi's method.

        D in [1, 2].  D=1 → smooth / persistent / trending, D=1.5 → Brownian,
        D=2 → white-noise / chaotic. Theoretical relation: D = 2 - H (H = Hurst).

        Pure Python, no numpy. Returns 1.5 (Brownian reference) on insufficient
        data or non-finite value. Unlike Hurst (works on log-returns), Higuchi
        is applied directly to the RAW series — the path-length scaling IS the signal.

        Reference: Higuchi, T. (1988). "Approach to an irregular time series on
        the basis of the fractal theory." Physica D 31(2): 277-283.
        """
        n = len(series)
        if n < k_max * 4:
            return 1.5

        # Higuchi is applied directly to the RAW series (not log-returns).
        ts = [float(x) for x in series]
        n_ts = len(ts)
        if not all(math.isfinite(x) for x in ts):
            ts = [x for x in ts if math.isfinite(x)]
            n_ts = len(ts)
            if n_ts < k_max * 4:
                return 1.5

        # For each scale k in 1..k_max:
        #   L_m(k) = (N-1) / (⌊(N-m)/k⌋ * k) * sum_{i=1..⌊(N-m)/k⌋} |x[m+i*k] - x[m+(i-1)*k]|
        #   L(k)   = (1/k) * sum_{m=0..k-1} L_m(k)   → then average over m
        # Then fit: D = -slope(log(L_k) vs log(1/k))
        # This normalization factor (N-1)/(N_m * k) is essential — it removes the
        # naive 1/k^{(D-2)} decay so the slope reflects pure fractal scaling.
        # Reference: Higuchi (1988) Physica D, Trisno et al. (2018 textbook).
        lags_k = []
        mean_Lk = []
        for k in range(1, k_max + 1):
            Lk_values = []
            for m in range(k):
                n_segments_here = (n_ts - m - 1) // k
                if n_segments_here < 1:
                    continue
                lk_sum = 0.0
                for i in range(1, n_segments_here + 1):
                    a = ts[m + i * k]
                    b = ts[m + (i - 1) * k]
                    lk_sum += abs(a - b)
                # Normalize by (N-1) so the curve length doesn't decay trivially.
                L_m = ((n_ts - 1) / (n_segments_here * k)) * lk_sum
                Lk_values.append(L_m)
            if Lk_values:
                lags_k.append(k)
                mean_Lk.append(sum(Lk_values) / len(Lk_values))

        if len(lags_k) < 3:
            return 1.5

        # Fit log(L_k) = (D-1) * log(1/k) + c → D = 1 + slope(log(L_k) vs log(1/k))
        # For SMOOTH line (D=1): L(k) const → slope = 0 → D = 1 ✓
        # For BROWNIAN (D=1.5): L(k) ~ (1/k)^0.5 → slope = -0.5 → D = 0.5  ✗ WRONG!
        #
        # Wait — let's re-derive carefully. For a fractal curve of dim D:
        #   L(k) ~ k^{-0.5}  for D=1.5 (Brownian)
        # log(L_k) = -0.5 * log(k) + c
        # As 1/k grows, log(1/k) = -log(k). So log(L) = -0.5 * (-log(1/k)) = +0.5 * log(1/k)
        # → slope(log(L_k) vs log(1/k)) = +0.5 → D-1 = 0.5 → D = 1.5 ✓
        # For SMOOTH D=1:  L(k) ~ const → log(L_k) ~ 0 * log(1/k) → slope=0 → D=1 ✓
        # For WHITE NOISE D=2: L(k) ~ 1/k → log(L_k) ~ +1 * log(1/k) → slope = 1 → D = 2 ✓
        # So D = slope + 1, where slope_of(log(L_k) vs log(1/k)). For an uptrend (smooth),
        # slope ≈ 0 → D ≈ 1. For chaotic, slope ≈ 1 → D ≈ 2. CORRECT.
        xs = [math.log(1.0 / k) for k in lags_k]
        ys = [math.log(L) for L in mean_Lk if L > 0]
        if len(ys) != len(xs) or len(xs) < 3:
            return 1.5

        n_pts = len(xs)
        x_mean = sum(xs) / n_pts
        y_mean = sum(ys) / n_pts
        num = sum((xs[i] - x_mean) * (ys[i] - y_mean) for i in range(n_pts))
        den = sum((xs[i] - x_mean) ** 2 for i in range(n_pts))
        if den == 0:
            return 1.5
        slope = num / den
        d = slope + 1.0  # D = 1 + slope(log(L_k) vs log(1/k)) — see derivation above
        try:
            d = float(d)
        except (TypeError, ValueError):
            return 1.5
        if not math.isfinite(d):
            return 1.5
        # Clamp to physical [1, 2] — D = 1 (smooth line), D = 2 (filling plane).
        return max(1.0, min(2.0, d))

    @classmethod
    def classify(cls, ohlcv: List[List[float]]) -> RegimeSignal:
        """
        Args:
            ohlcv: List of [open, high, low, close, volume] candles, newest last.

        Returns:
            RegimeSignal with regime enum, confidence 0-100, strategy template, diagnostics.
        """
        if len(ohlcv) < 30:
            return RegimeSignal(Regime.UNKNOWN, 0.0, "HOLD", {})

        closes = [c[3] for c in ohlcv]
        highs = [c[1] for c in ohlcv]
        lows = [c[2] for c in ohlcv]
        volumes = [c[4] for c in ohlcv]

        n = len(closes)
        period = 14

        # True Range => ATR
        tr_values = []
        for i in range(1, n):
            tr_values.append(cls._tr(highs[i], lows[i], closes[i - 1]))
        tr_values = [tr_values[0]] + tr_values
        atr_values = cls._rolling_mean(tr_values, period)

        # Directional Movement
        plus_dm = [0.0]
        minus_dm = [0.0]
        for i in range(1, n):
            up_move = highs[i] - highs[i - 1]
            down_move = lows[i - 1] - lows[i]
            pdm = up_move if up_move > down_move and up_move > 0 else 0.0
            ndm = down_move if down_move > up_move and down_move > 0 else 0.0
            plus_dm.append(pdm)
            minus_dm.append(ndm)

        smoothed_atr = cls._rolling_mean(atr_values, period)
        smoothed_pdm = cls._rolling_mean(plus_dm, period)
        smoothed_ndm = cls._rolling_mean(minus_dm, period)

        # HONEST FIX: original code computed DX = |pdm-ndm| / ATR * 100, which
        # is dimensionally wrong (DM and ATR share units but DX is a ratio of
        # directional strengths). The correct Wilder ADX uses DI = DM / ATR,
        # then DX = |+DI - -DI| / (+DI + -DI). Apply that fix.
        adx_values = []
        pdi_values: List[float] = []
        ndi_values: List[float] = []
        for i in range(n):
            if smoothed_atr[i] == 0:
                pdi_values.append(0.0)
                ndi_values.append(0.0)
                adx_values.append(0.0)
            else:
                pdi = (smoothed_pdm[i] / smoothed_atr[i]) * 100
                ndi = (smoothed_ndm[i] / smoothed_atr[i]) * 100
                pdi_values.append(pdi)
                ndi_values.append(ndi)
                di_sum = pdi + ndi
                dx = abs(pdi - ndi) / di_sum * 100 if di_sum > 0 else 0.0
                adx_values.append(dx)
        smoothed_adx = cls._rolling_mean(adx_values, period)

        current_adx = smoothed_adx[-1]
        current_pdi = pdi_values[-1]
        current_ndi = ndi_values[-1]
        avg_vol = sum(volumes[-10:]) / 10 if volumes[-10:] else 1
        vol_change = volumes[-1] / avg_vol if avg_vol > 0 else 1.0

        # BRUTAL FIX: add a secondary trend classifier (close-vs-SMA50, SMA50-vs-SMA200)
        # because pure Wilder ADX often misses low-volatility slow grinding trends.
        sma50 = cls._rolling_mean(closes, 50)[-1] if n >= 50 else (closes[-1] if closes else 0.0)
        sma200 = cls._rolling_mean(closes, 200)[-1] if n >= 200 else sma50
        slope_20_pct = ((closes[-1] - closes[-20]) / max(1e-9, closes[-20]) * 100) if n >= 20 else 0.0

        # Net trend score combines ADX, DI spread, and SMA slope.
        adx_strong = current_adx > 25
        di_bull = current_pdi > current_ndi * 1.2
        di_bear = current_ndi > current_pdi * 1.2
        sma_bull = closes[-1] > sma50 and sma50 > sma200
        sma_bear = closes[-1] < sma50 and sma50 < sma200
        slope_bull = slope_20_pct > 1.5
        slope_bear = slope_20_pct < -1.5

        # Re-evaluate slope with a tighter threshold (1.0% over 20 bars).
        bull_votes = sum([
            adx_strong and di_bull,
            sma_bull,
            slope_bull if slope_20_pct > 1.0 else False,
        ])
        bear_votes = sum([
            adx_strong and di_bear,
            sma_bear,
            slope_bear if slope_20_pct < -1.0 else False,
        ])

        # Tie-breaker: a strong DI spread alone is meaningful even if SMA hasn't
        # caught up yet (early-stage trend). Add 1 vote for strong DI divergence.
        if adx_strong and di_bull and current_pdi > current_ndi * 2.0:
            bull_votes += 1
        if adx_strong and di_bear and current_ndi > current_pdi * 2.0:
            bear_votes += 1

        # BRUTAL ENHANCEMENT: Hurst exponent (R/S analysis) adds a 4th voter.
        # H > 0.6  -> persistent / trending (votes in direction of slope)
        # H < 0.4  -> anti-persistent / mean-reverting (votes against trend, for CHOPPY)
        hurst = cls._hurst_exponent(closes)
        if hurst > 0.6 and slope_20_pct > 0.0:
            bull_votes += 1
        elif hurst > 0.6 and slope_20_pct < 0.0:
            bear_votes += 1
        # H < 0.4 -> subtract a vote from trend detection (anti-persistence)
        # by voting for CHOPPY later; we add an explicit mean_revert flag instead.
        mean_revert_signal = hurst < 0.4

        # 5TH VOTER: Higuchi Fractal Dimension (D), independent of Hurst (uses
        # a different estimator — useful cross-validation). Theoretical relation:
        #   D = 2 - H  (H = Hurst)
        #   D < 1.5  -> persistent / trending (corroborates H > 0.5)
        #   D > 1.5  -> anti-persistent / chaotic (corroborates H < 0.5)
        # We use D as a CONFIRMATION voter — only votes when H agrees with slope
        # direction AND D agrees (avoids sloppy_H edge cases).
        fractal_dim = cls._higuchi_fractal_dimension(closes)
        if (
            hurst > 0.6 and fractal_dim < 1.5 and slope_20_pct > 0.0
        ):
            bull_votes += 1
        elif (
            hurst > 0.6 and fractal_dim < 1.5 and slope_20_pct < 0.0
        ):
            bear_votes += 1
        # If fractal_dim > 1.6 (very chaotic) corroborate mean-revert
        if fractal_dim > 1.6:
            mean_revert_signal = mean_revert_signal or True

        if bull_votes >= 2:
            regime = Regime.TRENDING_UP
            strategy = "Trend_Following_Long"
        elif bear_votes >= 2:
            regime = Regime.TRENDING_DOWN
            strategy = "Trend_Following_Short"
        elif mean_revert_signal and (vol_change > 1.3 or current_adx < 20):
            # Hurst < 0.4 + low ADX + volume spike -> CHOPPY (good for MR band trades)
            regime = Regime.CHOPPY
            strategy = "Mean_Reversion_Band_Trading"
        elif adx_strong and not (di_bull or di_bear):
            regime = Regime.CHOPPY
            strategy = "Mean_Reversion_Band_Trading"
        elif vol_change > 1.3 and current_adx < 20:
            regime = Regime.CHOPPY
            strategy = "Mean_Reversion_Band_Trading"
        else:
            regime = Regime.RANGING
            strategy = "Range_Bound_Scalping"

        # Confidence reflects BOTH signal strength (ADX) AND voter consensus.
        # Old formula used only ADX/60 — a 2-vote weak agreement (e.g. faint
        # slope + faint SMA cross, ADX=12) would report confidence=0.20 even
        # though the decision was marginal. New formula:
        #   consensus = (max(bull_votes,bear_votes) / total_possible_voters)
        #   confidence = sqrt(adx_term * consensus_term) — geometric mean
        # so a 1-of-5 consensus with strong ADX cannot dominate, and a 5-of-5
        # consensus with weak ADX is also dampened. In CHOPPY/RANGING branches
        # (no bull/bear vote), confidence is driven by ADX alone (capped lower).
        adx_term = min(1.0, current_adx / 60.0)
        total_possible_voters = 5  # ADX/DI, SMA, slope, Hurst, Higuchi
        max_votes = max(bull_votes, bear_votes)
        consensus_term = min(1.0, max_votes / total_possible_voters)
        if regime in (Regime.TRENDING_UP, Regime.TRENDING_DOWN):
            # geometric mean — both must be present for high confidence
            import math as _m
            confidence = round(_m.sqrt(adx_term * consensus_term), 4)
            # safety floor: 0.05 minimum so downstream gates don't div-by-zero
            confidence = max(0.05, confidence)
        else:
            # CHOPPY/RANGING/UNKNOWN — confidence only from ADX (ranging)
            # with a discount when mean_revert_signal is weak (H near 0.5)
            confidence = max(0.05, round(0.5 * adx_term, 4))
        detailed = {
            "adx": round(current_adx, 2),
            "plus_di": round(current_pdi, 2),
            "minus_di": round(current_ndi, 2),
            "atr": round(atr_values[-1], 2),
            "volume_ratio": round(vol_change, 2),
            "hurst": round(hurst, 3),
            "fractal_dim": round(fractal_dim, 3),
        }

        return RegimeSignal(
            regime=regime,
            confidence=confidence,
            strategy=strategy,
            details=detailed,
        )


REGIME_STRATEGY_ROUTER: Dict[Regime, Dict[str, Any]] = {
    Regime.TRENDING_UP: {
        "primary": "Trend_Following_Long",
        "risk_mode": "aggressive",
        "max_position_pct": 0.25,
        "preferred_timeframes": ["15m", "1h"],
    },
    Regime.TRENDING_DOWN: {
        "primary": "Trend_Following_Short",
        "risk_mode": "defensive",
        "max_position_pct": 0.15,
        "preferred_timeframes": ["15m", "1h"],
    },
    Regime.CHOPPY: {
        "primary": "Mean_Reversion_Band_Trading",
        "risk_mode": "hedged",
        "max_position_pct": 0.10,
        "preferred_timeframes": ["5m", "15m"],
    },
    Regime.RANGING: {
        "primary": "Range_Bound_Scalping",
        "risk_mode": "neutral",
        "max_position_pct": 0.15,
        "preferred_timeframes": ["5m", "1h"],
    },
    Regime.UNKNOWN: {
        "primary": "HOLD",
        "risk_mode": "safe",
        "max_position_pct": 0.0,
        "preferred_timeframes": [],
    },
}