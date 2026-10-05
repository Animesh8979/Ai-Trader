"""Tests for PostOnlyPeggingEngine (Maker post-only execution and dynamic repegging)."""

from decimal import Decimal
import pytest

from godmode.execution.post_only_pegging import PostOnlyPeggingEngine, PegQuote


def test_peg_quote_buy_inside_spread():
    """Buy order must peg 1 tick inside spread (best_bid + tick_size)."""
    engine = PostOnlyPeggingEngine(default_tick_size=Decimal("0.01"))
    quote = engine.calculate_peg_quote(
        side="buy",
        best_bid=Decimal("68000.00"),
        best_ask=Decimal("68001.00"),
    )
    assert quote.price == Decimal("68000.01")
    assert quote.side == "buy"
    assert quote.post_only is True
    assert quote.order_type == "limit"
    assert quote.params.get("postOnly") is True


def test_peg_quote_sell_inside_spread():
    """Sell order must peg 1 tick inside spread (best_ask - tick_size)."""
    engine = PostOnlyPeggingEngine(default_tick_size=Decimal("0.01"))
    quote = engine.calculate_peg_quote(
        side="sell",
        best_bid=Decimal("68000.00"),
        best_ask=Decimal("68001.00"),
    )
    assert quote.price == Decimal("68000.99")
    assert quote.side == "sell"
    assert quote.post_only is True


def test_peg_quote_tight_spread():
    """When spread is 1 tick, peg sits at the touch without crossing."""
    engine = PostOnlyPeggingEngine(default_tick_size=Decimal("0.01"))
    buy_quote = engine.calculate_peg_quote(
        side="buy",
        best_bid=Decimal("68000.00"),
        best_ask=Decimal("68000.01"),
    )
    assert buy_quote.price == Decimal("68000.00")

    sell_quote = engine.calculate_peg_quote(
        side="sell",
        best_bid=Decimal("68000.00"),
        best_ask=Decimal("68000.01"),
    )
    assert sell_quote.price == Decimal("68000.01")


def test_should_repeg_threshold():
    """Dynamic repegging triggers when order drifts beyond threshold ticks."""
    engine = PostOnlyPeggingEngine(default_tick_size=Decimal("0.01"), repeg_tick_threshold=2)

    # Optimal quote for 68000.00 / 68001.00 is 68000.01
    # If resting order is at 68000.01, drift is 0 -> no repeg
    needs_repeg, new_price = engine.should_repeg(
        current_order_price=Decimal("68000.01"),
        current_best_bid=Decimal("68000.00"),
        current_best_ask=Decimal("68001.00"),
        side="buy",
    )
    assert needs_repeg is False
    assert new_price is None

    # Market moved up: best_bid is now 68000.05, optimal peg is 68000.06
    # Resting order at 68000.01 is 5 ticks away >= 2 ticks -> needs repeg!
    needs_repeg, new_price = engine.should_repeg(
        current_order_price=Decimal("68000.01"),
        current_best_bid=Decimal("68000.05"),
        current_best_ask=Decimal("68001.05"),
        side="buy",
    )
    assert needs_repeg is True
    assert new_price == Decimal("68000.06")
