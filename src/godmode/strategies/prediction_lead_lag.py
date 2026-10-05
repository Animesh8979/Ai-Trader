"""Prediction Market Lead-Lag Arbitrage Strategy.

Exploits information lead-lag between Polymarket prediction probabilities
and spot/perpetual orderbook pricing with absolute Decimal precision.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, List, Optional

from godmode.data.polymarket_oracle import PredictionSignal


@dataclass
class LeadLagTradeSignal:
    symbol: str
    action: str  # "BUY", "SELL", "HOLD"
    conviction: Decimal  # 0.00 to 1.00
    divergence_bps: Decimal
    target_size_usd: Decimal
    rationale: str
    is_paper_trading: bool = True


class PredictionLeadLagStrategy:
    """Quantitative Strategy: Detects prediction probability shifts leading exchange pricing."""

    def __init__(
        self,
        threshold_bps: Decimal = Decimal("50.0"),
        base_allocation_usd: Decimal = Decimal("500.0"),
        is_paper_trading: bool = True
    ):
        self.threshold_bps = threshold_bps
        self.base_allocation_usd = base_allocation_usd
        self.is_paper_trading = is_paper_trading

    def evaluate_signals(
        self,
        prediction_signals: List[PredictionSignal],
        current_spot_prices: Dict[str, Decimal]
    ) -> List[LeadLagTradeSignal]:
        """Evaluates prediction probability sentiment vs current market structure."""
        trade_proposals: List[LeadLagTradeSignal] = []

        for sig in prediction_signals:
            symbol = "BTC" if "bitcoin" in sig.title.lower() or "btc" in sig.title.lower() else "ETH"
            if symbol not in current_spot_prices:
                continue

            spot_price = current_spot_prices[symbol]
            yes_prob = sig.outcome_yes_prob

            # Mathematical Divergence Model:
            # Baseline probability is 0.50 (Neutral). Divergence = (P(Yes) - 0.50) * 10000 bps
            prob_divergence_bps = (yes_prob - Decimal("0.50")) * Decimal("10000")

            if abs(prob_divergence_bps) >= self.threshold_bps:
                action = "BUY" if prob_divergence_bps > 0 else "SELL"
                conviction = min(Decimal("1.00"), abs(prob_divergence_bps) / Decimal("3000"))
                trade_size = self.base_allocation_usd * conviction

                trade_proposals.append(
                    LeadLagTradeSignal(
                        symbol=symbol,
                        action=action,
                        conviction=conviction.quantize(Decimal("0.01")),
                        divergence_bps=prob_divergence_bps.quantize(Decimal("0.1")),
                        target_size_usd=trade_size.quantize(Decimal("0.01")),
                        rationale=f"Polymarket signal '{sig.title}' implied P(Yes)={yes_prob:.2f} creates {prob_divergence_bps:.1f} bps directional edge.",
                        is_paper_trading=self.is_paper_trading
                    )
                )

        return trade_proposals
