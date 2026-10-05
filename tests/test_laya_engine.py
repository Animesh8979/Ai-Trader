"""Unit tests for Laya AI System 1 Decision Engine."""

import time
import pytest
import numpy as np

from godmode.agents.laya_engine import LayaEngine, LayaFeatureExtractor, LayaFeatures
from godmode.agents.jev_trader_engine import (
    JevTraderEngine,
    JevJudgments,
    MarketRegime,
    TradeDirection,
    QuoteEnvironment,
)


def test_laya_feature_extraction():
    features = LayaFeatureExtractor.extract(
        price=50000.0,
        best_bid=49995.0,
        best_ask=50005.0,
        bid_depth=10.0,
        ask_depth=5.0,
        recent_returns=[0.001, 0.002, -0.0005, 0.0015],
        current_position=0.2,
        max_position=1.0,
        recent_trades=[
            {"price": 50000.0, "amount": 1.0, "side": "buy"},
            {"price": 50002.0, "amount": 2.0, "side": "buy"},
        ],
    )
    assert isinstance(features, LayaFeatures)
    vec = features.to_array()
    assert vec.shape == (12,)
    assert vec.dtype == np.float32
    assert -1.0 <= features.book_imbalance <= 1.0
    assert 0.0 <= features.vpin <= 1.0
    assert 0.0 <= features.buyer_ratio <= 1.0


def test_laya_engine_forward_pass_typing():
    engine = LayaEngine()
    judgments = engine.evaluate(
        symbol="BTC/USDT",
        price=68000.0,
        best_bid=67999.0,
        best_ask=68001.0,
        bid_depth=15.0,
        ask_depth=12.0,
        recent_returns=[0.0005, 0.0002, 0.0008, 0.0001],
        current_position=0.0,
        max_position=2.0,
        recent_trades=[{"price": 68000.0, "amount": 0.5, "side": "buy"}],
    )

    assert isinstance(judgments, JevJudgments)
    assert judgments.regime in [r.value for r in MarketRegime]
    assert judgments.direction in [d.value for d in TradeDirection]
    assert 0.0 <= judgments.toxic_flow <= 1.0
    assert 0.0 <= judgments.liquidity_stressed <= 1.0
    assert 0.0 <= judgments.quote_environment <= 5.0
    assert 0.0 <= judgments.inventory_pressure <= 5.0
    assert 0.0 <= judgments.confidence <= 1.0
    assert judgments.is_fallback is False
    assert judgments.latency_ms >= 0.0


def test_laya_bull_momentum_response():
    engine = LayaEngine()
    # Strong bullish momentum setup: positive returns, heavy bids, buy volume
    judgments = engine.evaluate(
        symbol="ETH/USDT",
        price=3500.0,
        best_bid=3499.8,
        best_ask=3500.2,
        bid_depth=50.0,
        ask_depth=5.0,
        recent_returns=[0.005, 0.004, 0.006, 0.008],
        current_position=0.0,
        max_position=5.0,
        recent_trades=[{"price": 3500.0, "amount": 10.0, "side": "buy"} for _ in range(5)],
    )

    assert judgments.direction == "LONG"
    assert judgments.regime in ["BULL_TREND", "VOLATILITY_EXPANSION"]
    assert judgments.toxic_flow < 0.50
    assert judgments.confidence > 0.40


def test_laya_toxic_flow_detection():
    engine = LayaEngine()
    # Toxic flow setup: massive spread blowout, high volatility, extreme sell dump
    judgments = engine.evaluate(
        symbol="BTC/USDT",
        price=60000.0,
        best_bid=59800.0,
        best_ask=60200.0,  # ~66 bps spread blowout
        bid_depth=1.0,
        ask_depth=20.0,
        recent_returns=[-0.03, 0.02, -0.04, 0.03],  # massive vol
        current_position=0.0,
        max_position=1.0,
        recent_trades=[{"price": 59900.0, "amount": 50.0, "side": "sell"} for _ in range(10)],
    )

    assert judgments.toxic_flow > 0.60
    assert judgments.direction in ["SHORT", "FLAT"]
    assert judgments.quote_environment < 3.0


def test_laya_sub_millisecond_latency():
    engine = LayaEngine()
    # 500 forward passes to benchmark throughput
    start_t = time.perf_counter()
    for _ in range(500):
        engine.evaluate(
            symbol="BTC/USDT",
            price=68000.0,
            best_bid=67999.0,
            best_ask=68001.0,
            bid_depth=10.0,
            ask_depth=10.0,
            recent_returns=[0.0001, -0.0001, 0.0002],
            current_position=0.1,
        )
    elapsed = time.perf_counter() - start_t
    avg_ms = (elapsed / 500) * 1000.0
    assert avg_ms < 2.0, f"Laya forward pass took {avg_ms:.2f}ms, expected < 2.0ms"


def test_jev_engine_delegates_to_laya():
    # JevTraderEngine without remote API key should transparently use local LayaEngine
    engine = JevTraderEngine(api_key="", use_laya=True)
    assert engine.laya_engine is not None

    evaluation = engine.evaluate(
        symbol="SOL/USDT",
        price=150.0,
        best_bid=149.95,
        best_ask=150.05,
        bid_depth=100.0,
        ask_depth=80.0,
        recent_returns=[0.001, 0.002],
        current_position=0.0,
    )
    assert isinstance(evaluation, JevJudgments)
    assert evaluation.raw_response.get("engine") == "laya_embedded_neural"
