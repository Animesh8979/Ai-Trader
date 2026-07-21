import polars as pl
import numpy as np

class AlphaZoo:
    """
    Alpha Zoo: Feature Engineering Engine (Inspired by Microsoft Qlib Alpha158).
    Generates robust statistical features (Momentum, Volatility, Regime indicators)
    for ML-based trading rather than pure RL.
    """
    
    @staticmethod
    def add_momentum_features(df: pl.DataFrame) -> pl.DataFrame:
        """Adds log returns, ROC, EMA crossover, and Wilder's RSI(14)."""
        df = df.with_columns([
            (pl.col("close") / pl.col("close").shift(1)).log().alias("log_return"),
            (pl.col("close") / pl.col("close").shift(5) - 1).alias("roc_5"),
            (pl.col("close") / pl.col("close").shift(15) - 1).alias("roc_15")
        ])

        # EMA crossover as momentum proxy
        df = df.with_columns([
            pl.col("close").ewm_mean(span=10, adjust=False).alias("ema_10"),
            pl.col("close").ewm_mean(span=50, adjust=False).alias("ema_50")
        ])
        df = df.with_columns(
            ((pl.col("ema_10") - pl.col("ema_50")) / pl.col("ema_50")).alias("ema_cross_dist")
        )

        # Wilder's RSI(14) — pure-python/polars implementation.
        # gain_t = max(delta, 0); loss_t = -min(delta, 0)
        # AvgGain uses Wilder smoothing: AG_t = (AG_{t-1} * 13 + gain_t) / 14
        # Polars: needs a recursive expression — but we approximate Wilder using
        # an EWM with span=2*period-1=27 and adjust=False, which gives the same
        # exponential decay coefficient α = 1/period.
        if "log_return" not in df.columns:
            df = df.with_columns((pl.col("close") / pl.col("close").shift(1)).log().alias("log_return"))
        delta = pl.col("close").diff()
        gain = pl.when(delta > 0).then(delta).otherwise(0.0)
        loss = pl.when(delta < 0).then(-delta).otherwise(0.0)
        # Wilder smoothing: EWM with span = 2*period - 1 = α of 1/period exactly
        period = 14
        wilder_span = 2 * period - 1
        avg_gain = gain.ewm_mean(span=wilder_span, adjust=False)
        avg_loss = loss.ewm_mean(span=wilder_span, adjust=False)
        rs = pl.when(avg_loss > 0).then(avg_gain / avg_loss).otherwise(pl.lit(float("inf")))
        rsi = pl.lit(100.0) - (pl.lit(100.0) / (pl.lit(1.0) + rs))
        df = df.with_columns(rsi.alias("rsi_14"))
        return df

    @staticmethod
    def add_volatility_features(df: pl.DataFrame) -> pl.DataFrame:
        """Adds rolling volatility and ATR proxies + EWMA vol (RiskMetrics λ=0.94)."""
        # Rolling standard deviation of log returns (historical volatility proxy)
        if "log_return" not in df.columns:
            df = df.with_columns((pl.col("close") / pl.col("close").shift(1)).log().alias("log_return"))

        df = df.with_columns([
            pl.col("log_return").rolling_std(window_size=20).alias("vol_20"),
            pl.col("log_return").rolling_std(window_size=60).alias("vol_60"),
        ])

        # EWMA volatility — RiskMetrics λ=0.94 standard for daily FX/equity vol surface.
        # σ_t^2 = (1-λ) * r_{t-1}^2 + λ * σ_{t-1}^2  (recursive). Polars ewm_mean on
        # squared returns gives a windowed approximation; we compute it directly:
        # ewm_mean of (log_return)^2 with span = 2/(1-λ) - 1 = 32.33 for λ=0.94.
        if "log_return" in df.columns:
            df = df.with_columns([
                (pl.col("log_return") ** 2).ewm_mean(span=33, adjust=False).sqrt()
                .alias("vol_ewma_94"),
            ])

        # High-Low Range
        df = df.with_columns(
            ((pl.col("high") - pl.col("low")) / pl.col("close")).alias("hl_range")
        )
        return df

    @staticmethod
    def add_fractional_diff_proxy(df: pl.DataFrame, d: float = 0.4, window: int = 5) -> pl.DataFrame:
        """
        Truncated-window fractional differentiation (Lopez de Prado, "Advances in
        Financial Machine Learning", ch. 5). For lag k, weight w_k = (d choose k)
        falling factorial = product_{i=0}^{k-1} (d-i) / k!. We truncate once
        |w_k| < 0.01 (a common practical threshold) or at `window` lags.

        Returns the fractionally-differenced close as `frac_diff_proxy`. Ponytail
        pure-Python: weights computed at runtime, then applied as a weighted sum
        of shifted closes. Stationary but memory-preserving — better than a 2-lag
        hack for distinguishing persistence from drift on noisy price series.
        """
        # Precompute Lopez de Prado fractional-diff weights w_k = (-1)^k * (d choose k),
        # where (d choose k) = (d choose k-1) * (d - (k-1)) / k. Truncate at |w_k| < 0.01
        # or at `window` lags.
        weights: list[float] = [1.0]  # w_0 = 1
        for k in range(1, window + 1):
            # w_k = -w_{k-1} * (d - (k-1)) / k  (sign flips each step due to (-1)^k factor)
            w = -weights[-1] * (d - (k - 1)) / k
            if abs(w) < 0.01:
                break
            weights.append(w)

        # Build weighted sum of lags: sum_k w_k * close.shift(k)  (w_0 = 1)
        # fill_null(0) on each shifted series so the weighted SUM stays finite at
        # the warmup rows (NaN would propagate through pl.lit(0.0) + ... arithmetic).
        expr = pl.lit(0.0)
        for k, w in enumerate(weights):
            expr = expr + (pl.lit(w) * pl.col("close").shift(k).fill_null(0.0))
        df = df.with_columns(expr.alias("frac_diff_proxy"))
        return df

    @classmethod
    def process_all(cls, df: pl.DataFrame) -> pl.DataFrame:
        """Process OHLCV dataframe through the entire Alpha Zoo pipeline."""
        df = cls.add_momentum_features(df)
        df = cls.add_volatility_features(df)
        df = cls.add_fractional_diff_proxy(df)
        return df.drop_nulls()

if __name__ == "__main__":
    # Test
    candles = [
        [1600000000 + i*60, 100 + i, 105 + i, 95 + i, 102 + i, 1000] for i in range(100)
    ]
    df = pl.DataFrame(candles, schema=["timestamp", "open", "high", "low", "close", "volume"], orient="row")
    processed = AlphaZoo.process_all(df)
    print("Processed DataFrame columns:", processed.columns)
    print("Sample feature 'frac_diff_proxy':", processed["frac_diff_proxy"].head(3).to_list())
