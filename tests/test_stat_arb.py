import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

import unittest
import numpy as np
import pandas as pd
from godmode.strategies.stat_arb import StatArbStrategy

class TestStatArbStrategy(unittest.TestCase):
    def setUp(self):
        self.strategy = StatArbStrategy(window=5, zscore_threshold=1.5)

    def test_compute_hedge_ratio(self):
        # Y = 2 * X + 1
        X = np.array([1, 2, 3, 4, 5])
        Y = np.array([3, 5, 7, 9, 11])
        hedge_ratio = self.strategy.compute_hedge_ratio(Y, X)
        self.assertAlmostEqual(hedge_ratio, 2.0, places=4)

    def test_generate_signals(self):
        # Create synthetic cointegrated series
        np.random.seed(42)
        x_prices = np.linspace(10, 20, 50) + np.random.normal(0, 0.1, 50)
        # y = 1.5 * x + noise
        y_prices = 1.5 * x_prices + np.random.normal(0, 0.1, 50)
        
        # Introduce a large spread deviation at the end
        y_prices[-1] += 5.0 

        df_x = pd.Series(x_prices, name='X')
        df_y = pd.Series(y_prices, name='Y')

        result = self.strategy.generate_signals(df_y, df_x)

        # Output shape check
        self.assertEqual(len(result), 50)
        self.assertIn('zscore', result.columns)
        self.assertIn('signal_Y', result.columns)
        self.assertIn('signal_X', result.columns)

        # Check last signal due to the deviation (Y spikes up, spread widens, zscore > threshold -> short spread)
        # Sell Y (-1), Buy X (hedge_ratio)
        last_row = result.iloc[-1]
        self.assertTrue(abs(last_row['zscore']) > 1.5)
        self.assertNotEqual(last_row['signal_Y'], 0.0)
        self.assertNotEqual(last_row['signal_X'], 0.0)

    def test_generate_signals_insufficient_data(self):
        df_x = pd.Series([1, 2, 3])
        df_y = pd.Series([2, 4, 6])
        with self.assertRaises(ValueError):
            self.strategy.generate_signals(df_y, df_x)

if __name__ == '__main__':
    unittest.main()
