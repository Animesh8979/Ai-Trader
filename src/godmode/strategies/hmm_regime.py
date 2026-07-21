import polars as pl
import numpy as np
import logging

logger = logging.getLogger(__name__)

class RegimeDetector:
    """
    Statistical Regime Detection Engine.
    Replaces heavy Black-Box RL (TensorTrade) with interpretable Market Regimes.
    Classifies the market into 4 distinct states based on AlphaZoo features:
    0: Bullish Trend (Low/Med Volatility, Positive Momentum)
    1: Bearish Trend (Low/Med Volatility, Negative Momentum)
    2: High Volatility Choppy (High Volatility, Mean-Reverting)
    3: Low Volatility Sideways (Low Volatility, Flat Momentum)
    """
    
    REGIME_BULL_TREND = 0
    REGIME_BEAR_TREND = 1
    REGIME_HIGH_VOL_CHOP = 2
    REGIME_LOW_VOL_SIDEWAYS = 3

    def __init__(self, df: pl.DataFrame):
        self.df = df

    def apply_regime_labels(self) -> pl.DataFrame:
        """
        Calculates rolling percentiles of volatility and momentum to dynamically 
        assign a regime label to each timestamp.
        Requires 'vol_60' and 'ema_cross_dist' from AlphaZoo.
        """
        if "vol_60" not in self.df.columns or "ema_cross_dist" not in self.df.columns:
            logger.error("[RegimeDetector] Missing required AlphaZoo features.")
            return self.df

        # Calculate rolling thresholds (e.g., top 75% for high vol)
        # Using a fixed lookback window to prevent lookahead bias (Walk-Forward safe)
        lookback = 1000  # Approx ~16 hours of 1m candles
        
        # We use a simple statistical heuristic for zero-bloat regime clustering
        df = self.df.with_columns([
            pl.col("vol_60").rolling_quantile(0.75, window_size=lookback).alias("vol_high_thresh"),
            pl.col("vol_60").rolling_quantile(0.25, window_size=lookback).alias("vol_low_thresh"),
            pl.col("ema_cross_dist").rolling_std(window_size=lookback).alias("mom_std")
        ])

        # Assign regimes based on conditions
        regime = (
            pl.when(pl.col("vol_60") > pl.col("vol_high_thresh"))
            .then(self.REGIME_HIGH_VOL_CHOP)
            .when((pl.col("vol_60") < pl.col("vol_low_thresh")) & (pl.col("ema_cross_dist").abs() < pl.col("mom_std")))
            .then(self.REGIME_LOW_VOL_SIDEWAYS)
            .when(pl.col("ema_cross_dist") > 0)
            .then(self.REGIME_BULL_TREND)
            .otherwise(self.REGIME_BEAR_TREND)
        )

        df = df.with_columns(regime.alias("market_regime"))
        return df

    @staticmethod
    def get_strategy_for_regime(regime: int) -> str:
        """Maps a detected regime to the optimal trading strategy."""
        mapping = {
            RegimeDetector.REGIME_BULL_TREND: "Trend_Following_Long",
            RegimeDetector.REGIME_BEAR_TREND: "Trend_Following_Short",
            RegimeDetector.REGIME_HIGH_VOL_CHOP: "Mean_Reversion_Band_Trading",
            RegimeDetector.REGIME_LOW_VOL_SIDEWAYS: "Market_Making_Tight_Spread"
        }
        return mapping.get(regime, "Halt_Trading")

if __name__ == "__main__":
    from godmode.data.alpha_zoo import AlphaZoo
    
    # Generate some dummy price action
    # Sine wave for choppy, linear for trend
    t = np.linspace(0, 100, 2000)
    prices = 100 + 10 * np.sin(t) + t
    
    candles = [
        [1600000000 + i*60, prices[i], prices[i]+1, prices[i]-1, prices[i], 1000] 
        for i in range(len(prices))
    ]
    
    df = pl.DataFrame(candles, schema=["timestamp", "open", "high", "low", "close", "volume"], orient="row")
    
    # Process through Alpha Zoo
    df = AlphaZoo.process_all(df)
    
    # Detect Regimes
    detector = RegimeDetector(df)
    df_regimed = detector.apply_regime_labels()
    
    print("Latest Regime:", df_regimed["market_regime"].tail(1).item())
    print("Strategy:", RegimeDetector.get_strategy_for_regime(df_regimed["market_regime"].tail(1).item()))
