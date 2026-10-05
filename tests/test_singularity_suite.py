"""Comprehensive Test Suite for Singularity Quant & Public APIs Ecosystem.

Follows Test Pyramid (Unit, Integration, E2E) and Quant Trading Architecture Laws.
"""

import math
from decimal import Decimal
from pathlib import Path
import pytest

from godmode.data.public_apis_harvester import PublicAPIsHarvester, PublicAPIFeed, PublicMarketSnapshot
from godmode.data.polymarket_oracle import PolymarketPredictionOracle, PredictionSignal
from godmode.strategies.prediction_lead_lag import PredictionLeadLagStrategy, LeadLagTradeSignal
from godmode.core.singularity_loop import ELOSSingularityLoop, BacktestMetrics


# ============================================================================
# 1. UNIT TESTS (70% - Mathematical Invariants & Pure Functions)
# ============================================================================

class TestUnitQuantPrecision:
    """U-001: Enforce Decimal precision across all financial metrics & signals."""

    def test_decimal_order_proposal_math(self):
        strat = PredictionLeadLagStrategy(
            threshold_bps=Decimal("50.0"),
            base_allocation_usd=Decimal("1000.00"),
            is_paper_trading=True
        )
        signals = [
            PredictionSignal(
                event_id="poly-btc-1",
                title="Bitcoin hits $100k",
                category="Crypto",
                outcome_yes_prob=Decimal("0.75"),
                outcome_no_prob=Decimal("0.25"),
                volume_24h=Decimal("500000.00"),
                sentiment_bias="BULLISH",
                timestamp=1700000000.0
            )
        ]
        spot_prices = {"BTC": Decimal("68000.00")}

        proposals = strat.evaluate_signals(signals, spot_prices)
        assert len(proposals) == 1
        prop = proposals[0]

        # Financial Law: Check all numeric outputs are Decimals, not floats
        assert isinstance(prop.target_size_usd, Decimal)
        assert isinstance(prop.divergence_bps, Decimal)
        assert isinstance(prop.conviction, Decimal)
        assert prop.action == "BUY"
        assert prop.divergence_bps == Decimal("2500.0")  # (0.75 - 0.50) * 10000
        assert prop.is_paper_trading is True

    def test_backtest_metrics_exact_formulae(self):
        """U-002: Verify Sharpe, Sortino, Max Drawdown & Profit Factor."""
        loop = ELOSSingularityLoop(min_sharpe_floor=Decimal("1.0"))
        # 4 trades: +500, -200, +800, -100 (Total = +1000)
        pnls = [Decimal("500.0"), Decimal("-200.0"), Decimal("800.0"), Decimal("-100.0")]
        metrics = loop.calculate_backtest_metrics(pnls, starting_equity=Decimal("10000.00"))

        assert metrics.total_trades == 4
        assert metrics.winning_trades == 2
        assert metrics.losing_trades == 2
        assert metrics.win_rate == Decimal("0.5000")
        assert metrics.gross_profit == Decimal("1300.00")
        assert metrics.gross_loss == Decimal("300.00")
        assert metrics.profit_factor == Decimal("4.33")
        assert metrics.sharpe_ratio > Decimal("0.0")
        assert metrics.sortino_ratio >= metrics.sharpe_ratio  # Sortino penalizes only downside
        assert metrics.max_drawdown_pct < Decimal("5.0")


# ============================================================================
# 2. INTEGRATION TESTS (20% - Catalog Search, Harvester & Oracle)
# ============================================================================

class TestIntegrationDataHarvester:
    """I-001: Verify public-apis README parsing and dynamic search."""

    def test_catalog_loader_and_search(self):
        harvester = PublicAPIsHarvester()
        catalog = harvester.load_catalog()
        assert len(catalog) > 100, "Catalog should contain hundreds of indexed public APIs"

        crypto_apis = harvester.search_endpoints("crypto", no_auth_only=True)
        assert len(crypto_apis) > 0
        assert all(api.auth.lower() == "no" for api in crypto_apis)

    def test_harvest_snapshot_generation(self):
        """I-002: Verify consolidated snapshot emits Decimal prices and valid timestamps."""
        harvester = PublicAPIsHarvester()
        snapshot = harvester.harvest_snapshot()

        assert isinstance(snapshot, PublicMarketSnapshot)
        assert "BTC" in snapshot.crypto_prices
        assert isinstance(snapshot.crypto_prices["BTC"], Decimal)
        assert "EUR" in snapshot.fx_rates
        assert len(snapshot.news_headlines) > 0
        assert len(snapshot.sources_used) >= 2


# ============================================================================
# 3. E2E SINGULARITY & HYPOTHESIS TESTS (10% - Self-Calibration Loop)
# ============================================================================

class TestE2ESingularityLoop:
    """E-001: Execute DO -> VERIFY -> DIAGNOSE -> CHANGE APPROACH -> REDO -> COMPARE -> COMMIT/REVERT -> LOG cycle."""

    def test_record_fill(self, tmp_path):
        mem_path = tmp_path / "iteration-log.jsonl"
        loop = ELOSSingularityLoop(memory_log_path=mem_path)

        fill_data = {
            "symbol": "BTC/USDT",
            "side": "buy",
            "qty": "0.5",
            "price": "68000.00",
            "realized_pnl": "125.50",
            "direction_predicted": "buy",
            "confidence": 0.82,
        }
        loop.record_fill(fill_data)
        assert len(loop.fill_history) == 1
        assert loop.fill_history[0]["realized_pnl"] == Decimal("125.50")
        assert loop.fill_history[0]["is_win"] is True

    def test_singularity_self_calibration_under_stress(self, tmp_path):
        mem_path = tmp_path / "iteration-log.jsonl"
        loop = ELOSSingularityLoop(memory_log_path=mem_path, min_sharpe_floor=Decimal("1.50"), max_drawdown_ceiling=Decimal("5.0"))

        # Stress test scenario with high volatility drawdown
        synthetic_run = [
            Decimal("-400.0"), Decimal("150.0"), Decimal("-350.0"),
            Decimal("800.0"), Decimal("-500.0"), Decimal("1100.0"), Decimal("-300.0")
        ]

        result = loop.run_singularity_cycle(synthetic_market_runs=[synthetic_run])

        assert result["result"] in ["COMMITTED", "REVERTED", "SUCCEEDED"]
        assert mem_path.exists()
        assert mem_path.stat().st_size > 0
        assert result["metrics_before"].gross_loss == Decimal("1550.00")
        assert result["metrics_before"].gross_profit == Decimal("2050.00")
        assert result["evidence"]["generation"] >= 1

        status = loop.get_status()
        assert status["generation"] >= 1
        assert status["iterations_run"] == 1
        assert len(status["recent_lessons"]) >= 1
        assert "active_parameters" in status

    def test_brier_score_calibration(self):
        """Verify Brier score calibration metric."""
        loop = ELOSSingularityLoop()
        # Perfect predictions: confidence 1.0 on wins, 0.0 on losses -> Brier score = 0.0
        pnls = [Decimal("10.0"), Decimal("-5.0")]
        confidences = [1.0, 0.0]
        metrics = loop.calculate_backtest_metrics(pnls, confidences)
        assert metrics.brier_score == Decimal("0.0000")

        # Inverted predictions: confidence 0.0 on wins, 1.0 on losses -> Brier score = 1.0
        confidences_bad = [0.0, 1.0]
        metrics_bad = loop.calculate_backtest_metrics(pnls, confidences_bad)
        assert metrics_bad.brier_score == Decimal("1.0000")

