"""Post-Only Maker Execution & Smart Queue Pegging Engine.

Implements the jarrodwatts/jev-trader market-making execution model:
Instead of paying taker fees and crossing the spread with market orders,
places post-only limit orders 1 tick inside the spread to capture spread yield
and earn maker rebates.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, Optional, Tuple

from godmode.core.logging import get_logger

log = get_logger("execution.post_only_pegging")


@dataclass
class PegQuote:
    price: Decimal
    side: str
    post_only: bool
    spread_bps: float
    expected_spread_capture_bps: float
    order_type: str = "limit"
    params: Dict[str, Any] = None  # type: ignore

    def __post_init__(self):
        if self.params is None:
            self.params = {
                "postOnly": True,
                "timeInForce": "PO",  # Post-Only for Binance/Bybit/CCXT
            }


class PostOnlyPeggingEngine:
    """Calculates post-only peg prices and manages repegging thresholds."""

    def __init__(self, default_tick_size: Decimal = Decimal("0.01"), repeg_tick_threshold: int = 2):
        self.default_tick_size = default_tick_size
        self.repeg_tick_threshold = repeg_tick_threshold

    def calculate_peg_quote(
        self,
        side: str,  # "buy" | "sell"
        best_bid: Decimal,
        best_ask: Decimal,
        tick_size: Optional[Decimal] = None,
    ) -> PegQuote:
        """Calculates optimal limit price pegged 1 tick inside the spread.
        
        If spread is only 1 tick, sits at the touch (best_bid or best_ask).
        """
        ts = tick_size or self.default_tick_size
        spread = best_ask - best_bid
        mid = (best_bid + best_ask) / Decimal("2")
        spread_bps = float((spread / mid) * Decimal("10000")) if mid > 0 else 0.0

        if side == "buy":
            # Peg 1 tick inside the spread if room exists
            if spread > ts:
                peg_price = best_bid + ts
            else:
                peg_price = best_bid
            expected_capture = float((spread / Decimal("2") / mid) * Decimal("10000")) if mid > 0 else 0.0
        else:  # sell
            if spread > ts:
                peg_price = best_ask - ts
            else:
                peg_price = best_ask
            expected_capture = float((spread / Decimal("2") / mid) * Decimal("10000")) if mid > 0 else 0.0

        return PegQuote(
            price=peg_price,
            side=side,
            post_only=True,
            spread_bps=round(spread_bps, 2),
            expected_spread_capture_bps=round(expected_capture, 2),
            order_type="limit",
            params={
                "postOnly": True,
                "timeInForce": "PO",
            }
        )

    def should_repeg(
        self,
        current_order_price: Decimal,
        current_best_bid: Decimal,
        current_best_ask: Decimal,
        side: str,
        tick_size: Optional[Decimal] = None,
    ) -> Tuple[bool, Optional[Decimal]]:
        """Determines if a resting post-only order has drifted and needs repegging."""
        ts = tick_size or self.default_tick_size
        target_quote = self.calculate_peg_quote(side, current_best_bid, current_best_ask, ts)
        tick_distance = abs(target_quote.price - current_order_price) / ts

        if tick_distance >= self.repeg_tick_threshold:
            log.info(
                f"[PostOnlyPegging] Order drifted by {tick_distance:.1f} ticks "
                f"(Current: {current_order_price}, Target: {target_quote.price}). Repegging required."
            )
            return True, target_quote.price

        return False, None
