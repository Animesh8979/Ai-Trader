import pytest
import pandas as pd
from pathlib import Path
from decimal import Decimal

from godmode.backtest.runner import run_backtest, map_timeframe
from godmode.core.config import load_config
from godmode.core.db import get_db, reset_db_singleton


@pytest.fixture
def sample_csv(tmp_path) -> Path:
    csv_file = tmp_path / "BTC_USDT_1h.csv"
    
    # Generate 48 hours of mock candle data
    timestamps = pd.date_range(start="2026-06-01", periods=48, freq="h")
    data = {
        "timestamp": timestamps.strftime("%Y-%m-%d %H:%M:%S"),
        # Trend: price moves up, then down, then crosses EMA
        "open": [100.0 + i * 0.5 for i in range(24)] + [112.0 - (i - 24) * 0.6 for i in range(24, 48)],
        "high": [101.0 + i * 0.5 for i in range(24)] + [113.0 - (i - 24) * 0.6 for i in range(24, 48)],
        "low": [99.0 + i * 0.5 for i in range(24)] + [111.0 - (i - 24) * 0.6 for i in range(24, 48)],
        "close": [100.5 + i * 0.5 for i in range(24)] + [111.5 - (i - 24) * 0.6 for i in range(24, 48)],
        "volume": [1.0] * 48,
    }
    df = pd.DataFrame(data)
    df.to_csv(csv_file, index=False)
    return csv_file


def test_map_timeframe():
    assert map_timeframe("1h") == "1-HOUR"
    assert map_timeframe("15m") == "15-MINUTE"
    assert map_timeframe("1d") == "1-DAY"
    assert map_timeframe("4h") == "4-HOUR"


def test_run_backtest_success(sample_csv, tmp_path):
    # Setup database file override for testing
    db_file = tmp_path / "test_godmode.sqlite3"
    import godmode.core.paths as paths
    orig_db_path = paths.DB_PATH
    paths.DB_PATH = db_file
    reset_db_singleton()

    try:
        # Run the backtest using our mock strategy & mock csv
        result = run_backtest(
            strategy_name="ema_crossover",
            data_path=str(sample_csv),
            start_date="2026-06-01",
        )
        assert result == 0

        # Assert database run metrics were saved
        db = get_db()
        runs = db.query("SELECT * FROM runs")
        assert len(runs) == 1
        assert runs[0]["mode"] == "backtest"
        assert runs[0]["status"] == "success"

        metrics = db.query("SELECT * FROM metrics")
        keys = {m["key"] for m in metrics}
        assert "starting_equity" in keys
        assert "final_equity" in keys
        assert "realized_pnl" in keys
    finally:
        # Restore original paths
        paths.DB_PATH = orig_db_path
        reset_db_singleton()
