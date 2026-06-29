import asyncio
import pytest
from unittest.mock import MagicMock, patch
from decimal import Decimal

from godmode.execution.live_runner import LiveRunner, compute_indicators
from godmode.risk.engine import RiskDecision, Verdict


def test_compute_indicators():
    # Construct 30 dummy candle elements [timestamp, open, high, low, close, volume]
    candles = [[i, 10.0 + i, 11.0 + i, 9.0 + i, 10.5 + i, 1.0] for i in range(30)]
    indicators = compute_indicators(candles)
    assert "rsi" in indicators
    assert "ema_fast" in indicators
    assert "ema_slow" in indicators
    assert indicators["close"] == 39.5


@patch("godmode.execution.live_runner.CryptoCcxtAdapter")
@patch("godmode.execution.live_runner.MultiAgentBrain")
def test_live_runner_step(mock_brain_class, mock_adapter_class, tmp_path):
    # Setup test DB file override
    db_file = tmp_path / "test_godmode.sqlite3"
    import godmode.core.paths as paths
    orig_db_path = paths.DB_PATH
    paths.DB_PATH = db_file
    
    import godmode.core.db as db_mod
    import godmode.core.killswitch as ks_mod
    
    db_mod.reset_db_singleton()
    db = db_mod.get_db()

    ks_mod._KS = None
    ks = ks_mod.get_kill_switch()
    orig_stop_file = ks.stop_file
    ks.stop_file = tmp_path / "STOP"

    try:
        # Mock CCXT adapter
        mock_adapter = MagicMock()
        mock_adapter_class.return_value = mock_adapter
        mock_adapter.fetch_balance.return_value = {
            "USDT": {"free": 50000.0, "total": 50000.0},
            "BTC": {"free": 0.0, "total": 0.0}
        }
        mock_adapter.exchange.fetch_ohlcv.return_value = [
            [i, 10, 11, 9, 10, 1] for i in range(30)
        ]
        
        # Mock Brain
        mock_brain = MagicMock()
        mock_brain_class.return_value = mock_brain
        mock_brain.decide_trade.return_value = {
            "action": "buy",
            "size": 0.05,
            "reason": "Indicator bullish breakout"
        }
        
        # Instantiate LiveRunner
        runner = LiveRunner()
        
        # Mock risk engine decision (approve)
        runner.risk_engine = MagicMock()
        runner.risk_engine.evaluate_and_enforce.return_value = RiskDecision(
            verdict=Verdict.APPROVE,
            approved_qty=Decimal("0.05"),
            reasons=[]
        )
        
        # Setup run properties
        runner._running = True
        runner._run_id = db.start_run(mode="paper")
        runner.config.app.decision_interval_seconds = 0.001
        
        # Run event loop for exactly one cycle then exit
        # We hook into decided_trade to set self._running = False so the loop terminates gracefully
        original_decide = mock_brain.decide_trade
        def mock_decide(*args, **kwargs):
            runner._running = False
            return original_decide(*args, **kwargs)
        mock_brain.decide_trade = mock_decide

        # Run loop body
        asyncio.run(runner._main_loop())
        
        # Verify order records were written to SQLite
        orders = db.query("SELECT * FROM orders")
        assert len(orders) == 1
        assert orders[0]["side"] == "buy"
        assert orders[0]["qty"] == "0.05"
        
        fills = db.query("SELECT * FROM fills")
        assert len(fills) == 1
        assert fills[0]["qty"] == "0.05"
        
        positions = db.query("SELECT * FROM positions")
        assert len(positions) == 1
        assert positions[0]["qty"] == "0.05"
    
    finally:
        ks.stop_file = orig_stop_file
        ks_mod._KS = None
        paths.DB_PATH = orig_db_path
        db_mod.reset_db_singleton()
