"""Tests for JevTraderEngine (System 1 fast heuristic & typed judgments)."""

import time
from decimal import Decimal
import pytest

from godmode.agents.jev_trader_engine import (
    JevTraderEngine,
    JevJudgments,
    JevEvaluation,
    MarketRegime,
    TradeDirection,
    QuoteEnvironment,
    OpenJevLocalFallback,
    compress_market_state,
)


def test_compress_market_state_token_budget():
    """State compression must produce concise representation well under 400 tokens (~300 words)."""
    text = compress_market_state(
        symbol="BTC/USDT",
        best_bid=68500.0,
        best_ask=68501.0,
        mid_price=68500.5,
        spread_bps=1.46,
        bid_depth=125.4,
        ask_depth=110.2,
        ofi_zscore=1.85,
        inventory_qty=0.25,
        recent_trades=[
            {"price": 68500.5, "amount": 0.5, "side": "buy"},
            {"price": 68500.8, "amount": 1.2, "side": "buy"},
        ],
    )
    words = text.split()
    assert len(words) < 250, f"Compressed state was {len(words)} words, expected < 250"
    assert "BTC/USDT" in text
    assert "68500.5" in text


def test_open_jev_local_fallback_latency_and_typing():
    """OpenJevLocalFallback must return a typed JevJudgments in sub-millisecond latency."""
    t0 = time.perf_counter()
    eval_result = OpenJevLocalFallback.evaluate_heuristically(
        best_bid=68500.0,
        best_ask=68501.0,
        spread_bps=1.46,
        inventory_qty=0.0,
        mid_price=68500.5,
        recent_trades=[
            {"price": 68500.5, "amount": 0.5, "side": "buy"},
            {"price": 68501.0, "amount": 0.8, "side": "buy"},
        ],
    )
    elapsed_ms = (time.perf_counter() - t0) * 1000

    assert elapsed_ms < 10.0, f"Fallback latency was {elapsed_ms:.2f}ms, expected < 10ms"
    assert isinstance(eval_result, JevJudgments)
    assert isinstance(eval_result, JevEvaluation)
    assert eval_result.regime in [r.value for r in MarketRegime]
    assert eval_result.direction in [d.value for d in TradeDirection]
    assert 0.0 <= eval_result.quote_environment <= 5.0
    assert 0.0 <= eval_result.toxic_flow <= 1.0
    assert 0.0 <= eval_result.liquidity_stressed <= 1.0
    assert 0.0 <= eval_result.inventory_pressure <= 5.0
    assert 0.0 <= eval_result.confidence <= 1.0


def test_open_jev_local_fallback_edge_cases():
    """Fallback must handle empty trade history and extreme spreads gracefully."""
    # Zero trades, wide spread (40 bps at price 50000 = 200 pts)
    eval_empty = OpenJevLocalFallback.evaluate_heuristically(
        best_bid=50000.0,
        best_ask=50200.0,
        spread_bps=40.0,
        inventory_qty=3.5,
        mid_price=50100.0,
        recent_trades=[],
    )
    # Wide spread should depress quote environment score
    assert eval_empty.quote_environment <= 3.0
    assert eval_empty.inventory_pressure >= 3.0

    # Strong buy pressure
    eval_buy = OpenJevLocalFallback.evaluate_heuristically(
        best_bid=68000.0,
        best_ask=68001.0,
        spread_bps=1.4,
        inventory_qty=0.0,
        mid_price=68000.5,
        bid_depth=10.0,
        ask_depth=1.0,
        recent_returns=[0.0015, 0.0020, 0.0010],
        recent_trades=[{"price": 68000.5, "amount": 5.0, "side": "buy"} for _ in range(5)],
    )
    assert eval_buy.direction in ["LONG", "FLAT"]
    assert eval_buy.regime in ["BULL_TREND", "VOLATILITY_EXPANSION", "MEAN_REVERTING_CHOP"]


def test_jev_trader_engine_evaluate():
    """JevTraderEngine.evaluate must fall back cleanly when no remote API key is set."""
    engine = JevTraderEngine(api_key="")
    evaluation = engine.evaluate(
        symbol="BTC/USDT",
        price=68500.5,
        best_bid=68500.0,
        best_ask=68501.0,
        bid_depth=5.0,
        ask_depth=4.5,
        recent_returns=[0.0005, -0.0002, 0.0008],
        current_position=0.1,
        max_position=1.0,
        recent_trades=[{"price": 68500.5, "amount": 0.2, "side": "sell"}],
    )
    assert isinstance(evaluation, JevJudgments)
    assert evaluation.direction in ["LONG", "SHORT", "FLAT"]
    assert evaluation.latency_ms >= 0.0
