import numpy as np
import pandas as pd

class StatArbStrategy:
    """
    Statistical Arbitrage & Pairs Trading Engine (Engle-Granger inspired).
    Calculates dynamic hedge ratios and spread z-scores to generate market-neutral signals.
    """
    def __init__(self, window=20, zscore_threshold=2.0):
        self.window = window
        self.zscore_threshold = zscore_threshold

    def compute_hedge_ratio(self, y, x):
        """
        Static computation of hedge ratio using Ordinary Least Squares (OLS) proxy.
        """
        if len(y) != len(x) or len(y) < 2:
            return 1.0
        slope, _ = np.polyfit(x, y, 1)
        return slope

    def generate_signals(self, df_y, df_x):
        """
        Generates trading signals for a pair of assets based on statistical arbitrage.
        df_y: pandas Series of prices for asset Y
        df_x: pandas Series of prices for asset X
        Returns a DataFrame containing spread, z-score, and signals for both assets.
        """
        # Ensure alignment
        df = pd.concat([df_y, df_x], axis=1).dropna()
        df.columns = ['Y', 'X']
        
        if len(df) < self.window:
            raise ValueError("Not enough data to compute signals.")
            
        # Rolling covariance and variance to calculate dynamic hedge ratio (beta)
        rolling_cov = df['Y'].rolling(window=self.window).cov(df['X'])
        rolling_var = df['X'].rolling(window=self.window).var()
        
        df['hedge_ratio'] = rolling_cov / rolling_var
        
        # Fallback to static hedge ratio for initial window (optional, but keep it clean and just use NaN)
        # Spread = Y - hedge_ratio * X
        df['spread'] = df['Y'] - df['hedge_ratio'] * df['X']
        
        # Rolling mean and std of spread for Z-score
        df['spread_mean'] = df['spread'].rolling(window=self.window).mean()
        df['spread_std'] = df['spread'].rolling(window=self.window).std()
        
        # Avoid division by zero
        df['spread_std'] = df['spread_std'].replace(0, np.nan)
        
        df['zscore'] = (df['spread'] - df['spread_mean']) / df['spread_std']
        
        df['signal_Y'] = 0.0
        df['signal_X'] = 0.0
        
        # Vectorized positional signals
        # Long spread (Buy Y, Sell X) when zscore < -threshold
        long_spread = df['zscore'] < -self.zscore_threshold
        # Short spread (Sell Y, Buy X) when zscore > threshold
        short_spread = df['zscore'] > self.zscore_threshold
        
        df.loc[long_spread, 'signal_Y'] = 1.0
        df.loc[long_spread, 'signal_X'] = -df.loc[long_spread, 'hedge_ratio']
        
        df.loc[short_spread, 'signal_Y'] = -1.0
        df.loc[short_spread, 'signal_X'] = df.loc[short_spread, 'hedge_ratio']
        
        return df
