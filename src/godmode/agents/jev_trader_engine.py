"""Jev Trader System 1 Engine — High-speed typed decision engine.

Adopts the buberlo/jev-trader architecture:
1. Feature Engine: Compresses market state into a compact <400-token payload.
2. Atomic Judgments: Emits 6 distinct typed judgments in a single forward pass:
   - regime: BULL_TREND | BEAR_TREND | MEAN_REVERTING_CHOP | VOLATILITY_EXPANSION
   - direction: LONG | SHORT | FLAT
   - toxic_flow: float (probability in [0.0, 1.0])
   - liquidity_stressed: float (probability in [0.0, 1.0])
   - quote_environment: float (0.0 to 5.0 rating)
   - inventory_pressure: float (0.0 to 5.0 rating)
3. Offline Fallback: High-precision deterministic OpenJev fallback when no external API key is present.
"""

from __future__ import annotations

import math
import os
import time
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from typing import Any, Dict, List, Optional

from godmode.core.logging import get_logger

from enum import Enum

log = get_logger("agents.jev_trader_engine")


class MarketRegime(str, Enum):
    BULL_TREND = "BULL_TREND"
    BEAR_TREND = "BEAR_TREND"
    MEAN_REVERTING_CHOP = "MEAN_REVERTING_CHOP"
    VOLATILITY_EXPANSION = "VOLATILITY_EXPANSION"


class TradeDirection(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    FLAT = "FLAT"


class QuoteEnvironment(str, Enum):
    UNUSABLE = "UNUSABLE"
    DANGEROUS = "DANGEROUS"
    MEDIOCRE = "MEDIOCRE"
    ACCEPTABLE = "ACCEPTABLE"
    GOOD = "GOOD"
    OPTIMAL = "OPTIMAL"


@dataclass
class JevJudgments:
    """The 6 atomic typed judgments emitted by System 1."""
    regime: str  # BULL_TREND, BEAR_TREND, MEAN_REVERTING_CHOP, VOLATILITY_EXPANSION
    direction: str  # LONG, SHORT, FLAT
    toxic_flow: float  # Probability of adverse selection / predatory flow [0.0, 1.0]
    liquidity_stressed: float  # Probability of order book thinning / liquidity vacuum [0.0, 1.0]
    quote_environment: float  # Spread & quote stability rating [0.0 = terrible, 5.0 = optimal]
    inventory_pressure: float  # Inventory risk score [0.0 = neutral/safe, 5.0 = extreme risk]
    confidence: float  # Calibrated decision confidence [0.0, 1.0]
    latency_ms: float = 0.0
    is_fallback: bool = False
    raw_response: Optional[Dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# Type alias for JevEvaluation
JevEvaluation = JevJudgments



def compress_market_state(
    symbol: str,
    best_bid: float,
    best_ask: float,
    mid_price: float,
    spread_bps: float,
    bid_depth: float = 1.0,
    ask_depth: float = 1.0,
    ofi_zscore: float = 0.0,
    inventory_qty: float = 0.0,
    recent_trades: Optional[List[Dict[str, Any]]] = None,
    recent_returns: Optional[List[float]] = None,
    max_position: float = 1.0,
) -> str:
    """Helper function to compress market state into a compact string context."""
    engine = JevTraderEngine(api_key="")
    return engine.compress_state(
        symbol=symbol,
        price=mid_price,
        best_bid=best_bid,
        best_ask=best_ask,
        bid_depth=bid_depth,
        ask_depth=ask_depth,
        recent_returns=recent_returns or [0.0],
        current_position=inventory_qty,
        max_position=max_position,
        recent_trades=recent_trades,
    )


class JevTraderEngine:
    """System 1 decision engine supporting Laya AI (local), TypeSafe AI Jev (cloud), and OpenJev fallback."""

    def __init__(self, api_key: Optional[str] = None, use_laya: bool = True):
        self.api_key = api_key or os.environ.get("TYPESAFE_API_KEY", "")
        self.client = None
        self.use_laya = use_laya
        self.laya_engine = None

        if self.use_laya:
            try:
                from godmode.agents.laya_engine import LayaEngine
                self.laya_engine = LayaEngine()
                log.info("[JevTraderEngine] Initialized with local Laya AI System 1 engine")
            except Exception as e:
                log.warning(f"[JevTraderEngine] Failed initializing LayaEngine: {e}")

        if self.api_key:
            try:
                from typesafe_sdk import TypeSafeClient  # type: ignore
                self.client = TypeSafeClient(api_key=self.api_key)
                log.info("[JevTraderEngine] Initialized with live TypeSafe AI client")
            except Exception as e:
                log.warning(f"[JevTraderEngine] Failed to initialize TypeSafeClient: {e}.")
                self.client = None
        elif not self.laya_engine:
            log.info("[JevTraderEngine] No TYPESAFE_API_KEY or LayaEngine found. Running deterministic OpenJev fallback.")

    def compress_state(
        self,
        symbol: str,
        price: float,
        best_bid: float,
        best_ask: float,
        bid_depth: float,
        ask_depth: float,
        recent_returns: List[float],
        current_position: float,
        max_position: float = 1.0,
        recent_trades: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """Compresses live market state into a high-density string context (<400 tokens)."""
        spread_bps = ((best_ask - best_bid) / price * 10000) if price > 0 else 0.0
        total_depth = bid_depth + ask_depth
        book_imbalance = ((bid_depth - ask_depth) / total_depth) if total_depth > 0 else 0.0

        n = len(recent_returns)
        mean_ret = (sum(recent_returns) / n) if n > 0 else 0.0
        variance = (sum((r - mean_ret) ** 2 for r in recent_returns) / max(1, n - 1)) if n > 1 else 0.0
        realized_vol = math.sqrt(variance) * 10000  # in bps

        # Order flow toxicity estimate (approximate VPIN from recent trades)
        vpin_metric = 0.5
        if recent_trades and len(recent_trades) >= 5:
            buy_vol = sum(t.get("amount", 0) for t in recent_trades if t.get("side") == "buy")
            sell_vol = sum(t.get("amount", 0) for t in recent_trades if t.get("side") == "sell")
            tot = buy_vol + sell_vol
            if tot > 0:
                vpin_metric = abs(buy_vol - sell_vol) / tot

        inv_ratio = (current_position / max_position) if max_position > 0 else 0.0

        return (
            f"SYM:{symbol} | P:{price:.2f} | B:{best_bid:.2f} | A:{best_ask:.2f} | "
            f"SPD_BPS:{spread_bps:.1f} | IMB:{book_imbalance:+.2f} | "
            f"VOL_BPS:{realized_vol:.1f} | RET_M5:{mean_ret * 100:+.3f}% | "
            f"VPIN:{vpin_metric:.2f} | POS:{current_position:.3f}/{max_position:.3f} ({inv_ratio * 100:+.0f}%)"
        )

    def evaluate(
        self,
        symbol: str,
        price: float,
        best_bid: float,
        best_ask: float,
        bid_depth: float,
        ask_depth: float,
        recent_returns: List[float],
        current_position: float,
        max_position: float = 1.0,
        recent_trades: Optional[List[Dict[str, Any]]] = None,
    ) -> JevJudgments:
        """Evaluates market state and returns the 6 atomic typed judgments."""
        t0 = time.perf_counter()
        state_str = self.compress_state(
            symbol=symbol,
            price=price,
            best_bid=best_bid,
            best_ask=best_ask,
            bid_depth=bid_depth,
            ask_depth=ask_depth,
            recent_returns=recent_returns,
            current_position=current_position,
            max_position=max_position,
            recent_trades=recent_trades,
        )

        # 1. Try Live TypeSafe Jev API
        if self.client:
            try:
                from typesafe_sdk import Choice, Noul, Score  # type: ignore

                response = self.client.system_one(
                    state=state_str,
                    questions={
                        "regime": Choice(
                            instructions="Classify market regime based on spread, imbalance, and volatility.",
                            criteria={
                                "BULL_TREND": "Sustained upward momentum, positive book imbalance",
                                "BEAR_TREND": "Sustained downward momentum, negative book imbalance",
                                "MEAN_REVERTING_CHOP": "Low volatility, tight spread, oscillating price",
                                "VOLATILITY_EXPANSION": "Spike in realized volatility, widening spread"
                            }
                        ),
                        "direction": Choice(
                            instructions="Select immediate tactical directional bias.",
                            criteria={
                                "LONG": "Favorable risk-reward for long entry/peg",
                                "SHORT": "Favorable risk-reward for short entry/peg",
                                "FLAT": "Uncertainty or adverse conditions; stay flat"
                            }
                        ),
                        "toxic_flow": Noul(
                            instructions="Is there a high probability of adverse selection or predatory order flow?"
                        ),
                        "liquidity_stressed": Noul(
                            instructions="Is order book depth dangerously thin or subject to liquidity vacuum?"
                        ),
                        "quote_environment": Score(
                            instructions="Rate the safety and profitability of quoting inside the spread.",
                            criteria=["Unusable", "Dangerous", "Mediocre", "Acceptable", "Good", "Optimal"]
                        ),
                        "inventory_pressure": Score(
                            instructions="Rate the inventory risk level of current position.",
                            criteria=["Zero", "Minimal", "Moderate", "Elevated", "High", "Critical"]
                        )
                    }
                )

                latency_ms = (time.perf_counter() - t0) * 1000.0
                answers = response.answers
                regime_ans = answers["regime"]
                dir_ans = answers["direction"]

                return JevJudgments(
                    regime=regime_ans.choice,
                    direction=dir_ans.choice,
                    toxic_flow=float(answers["toxic_flow"].noul),
                    liquidity_stressed=float(answers["liquidity_stressed"].noul),
                    quote_environment=float(answers["quote_environment"].score),
                    inventory_pressure=float(answers["inventory_pressure"].score),
                    confidence=float(dir_ans.confidence),
                    latency_ms=round(latency_ms, 2),
                    is_fallback=False,
                    raw_response=response.to_dict() if hasattr(response, "to_dict") else {},
                )
            except Exception as e:
                log.warning(f"[JevTraderEngine] Live Jev call failed: {e}. Falling back to Laya/OpenJev.")

        # 2. Local Laya AI System 1 Engine (Fast on-device neural decision pass)
        if self.laya_engine:
            try:
                return self.laya_engine.evaluate(
                    symbol=symbol,
                    price=price,
                    best_bid=best_bid,
                    best_ask=best_ask,
                    bid_depth=bid_depth,
                    ask_depth=ask_depth,
                    recent_returns=recent_returns,
                    current_position=current_position,
                    max_position=max_position,
                    recent_trades=recent_trades,
                )
            except Exception as e:
                log.warning(f"[JevTraderEngine] Laya evaluation error: {e}. Falling back to OpenJev.")

        # 3. Deterministic OpenJev Fallback
        return self._openjev_fallback(
            price=price,
            best_bid=best_bid,
            best_ask=best_ask,
            bid_depth=bid_depth,
            ask_depth=ask_depth,
            recent_returns=recent_returns,
            current_position=current_position,
            max_position=max_position,
            t0=t0,
        )

    def _openjev_fallback(
        self,
        price: float,
        best_bid: float,
        best_ask: float,
        bid_depth: float,
        ask_depth: float,
        recent_returns: List[float],
        current_position: float,
        max_position: float,
        t0: float,
    ) -> JevJudgments:
        """High-precision deterministic System 1 decision engine (<2ms)."""
        spread_bps = ((best_ask - best_bid) / price * 10000) if price > 0 else 0.0
        total_depth = bid_depth + ask_depth
        book_imbalance = ((bid_depth - ask_depth) / total_depth) if total_depth > 0 else 0.0

        n = len(recent_returns)
        mean_ret = (sum(recent_returns) / n) if n > 0 else 0.0
        variance = (sum((r - mean_ret) ** 2 for r in recent_returns) / max(1, n - 1)) if n > 1 else 0.0
        realized_vol_bps = math.sqrt(variance) * 10000

        # 1. Toxic Flow Probability (high spread + extreme imbalance + high vol)
        toxic_flow_prob = 0.10
        if spread_bps > 10.0:
            toxic_flow_prob += 0.30
        if abs(book_imbalance) > 0.60:
            toxic_flow_prob += 0.25
        if realized_vol_bps > 40.0:
            toxic_flow_prob += 0.25
        toxic_flow_prob = min(0.99, max(0.01, toxic_flow_prob))

        # 2. Liquidity Stressed Probability (low total depth or wide spread)
        liquidity_stressed_prob = 0.10
        if total_depth < 0.5:
            liquidity_stressed_prob += 0.40
        if spread_bps > 12.0:
            liquidity_stressed_prob += 0.35
        liquidity_stressed_prob = min(0.99, max(0.01, liquidity_stressed_prob))

        # 3. Quote Environment Score (0.0 to 5.0)
        quote_score = 4.0
        if spread_bps > 15.0:
            quote_score -= 2.0
        elif spread_bps < 3.0:
            quote_score += 1.0
        if toxic_flow_prob > 0.50:
            quote_score -= 1.5
        if liquidity_stressed_prob > 0.50:
            quote_score -= 1.0
        quote_score = min(5.0, max(0.0, quote_score))

        # 4. Inventory Pressure Score (0.0 to 5.0)
        pos_ratio = abs(current_position / max_position) if max_position > 0 else 0.0
        inventory_pressure_score = min(5.0, pos_ratio * 5.0)

        # 5. Regime Classification
        if realized_vol_bps > 50.0:
            regime = "VOLATILITY_EXPANSION"
        elif mean_ret > 0.0008 and book_imbalance > 0.20:
            regime = "BULL_TREND"
        elif mean_ret < -0.0008 and book_imbalance < -0.20:
            regime = "BEAR_TREND"
        else:
            regime = "MEAN_REVERTING_CHOP"

        # 6. Direction & Calibrated Confidence
        direction = "FLAT"
        confidence = 0.50

        if toxic_flow_prob > 0.70 or liquidity_stressed_prob > 0.75:
            direction = "FLAT"
            confidence = 0.90  # Confident in staying out
        elif regime == "BULL_TREND" and inventory_pressure_score < 3.5:
            direction = "LONG"
            confidence = min(0.88, 0.55 + abs(book_imbalance) * 0.30)
        elif regime == "BEAR_TREND" and inventory_pressure_score < 3.5:
            direction = "SHORT"
            confidence = min(0.88, 0.55 + abs(book_imbalance) * 0.30)
        elif regime == "MEAN_REVERTING_CHOP":
            # Contrarian fade at book extremes
            if book_imbalance > 0.40 and current_position < max_position * 0.5:
                direction = "LONG"
                confidence = 0.65
            elif book_imbalance < -0.40 and current_position > -max_position * 0.5:
                direction = "SHORT"
                confidence = 0.65
            else:
                direction = "FLAT"
                confidence = 0.60

        latency_ms = (time.perf_counter() - t0) * 1000.0

        return JevJudgments(
            regime=regime,
            direction=direction,
            toxic_flow=round(toxic_flow_prob, 3),
            liquidity_stressed=round(liquidity_stressed_prob, 3),
            quote_environment=round(quote_score, 1),
            inventory_pressure=round(inventory_pressure_score, 1),
            confidence=round(confidence, 3),
            latency_ms=round(latency_ms, 2),
            is_fallback=True,
            raw_response={"openjev_version": "1.0", "algorithm": "deterministic_microstructure"},
        )


class OpenJevLocalFallback:
    """Convenience helper for standalone fast heuristic evaluation (<2ms)."""

    _engine_instance: Optional[JevTraderEngine] = None

    @classmethod
    def evaluate_heuristically(
        cls,
        best_bid: float,
        best_ask: float,
        spread_bps: float,
        inventory_qty: float,
        mid_price: float,
        recent_trades: Optional[List[Dict[str, Any]]] = None,
        recent_returns: Optional[List[float]] = None,
        bid_depth: float = 1.0,
        ask_depth: float = 1.0,
        max_position: float = 1.0,
    ) -> JevJudgments:
        if cls._engine_instance is None:
            cls._engine_instance = JevTraderEngine(api_key="")
        return cls._engine_instance._openjev_fallback(
            price=mid_price,
            best_bid=best_bid,
            best_ask=best_ask,
            bid_depth=bid_depth,
            ask_depth=ask_depth,
            recent_returns=recent_returns or [0.0],
            current_position=inventory_qty,
            max_position=max_position,
            t0=time.perf_counter(),
        )

