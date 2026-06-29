"""Decimal money math.

Rule of the house: **never use float for money or quantities.** Floats carry binary
rounding error that silently corrupts accounting and order sizing. Everything monetary
flows through `Decimal` here. Floats are converted via `str()` so e.g. 0.1 stays 0.1.
"""

from __future__ import annotations

from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal, getcontext
from typing import Union

# Plenty of precision for prices * quantities without overflow surprises.
getcontext().prec = 34

Number = Union[int, float, str, Decimal]

ZERO = Decimal("0")
ONE = Decimal("1")


def D(value: Number) -> Decimal:
    """Convert any number-like value to Decimal safely (floats via str())."""
    if isinstance(value, Decimal):
        return value
    if isinstance(value, float):
        return Decimal(str(value))
    return Decimal(value)


def quantize(value: Number, increment: Number, rounding: str = ROUND_DOWN) -> Decimal:
    """Round `value` to a whole multiple of `increment` (e.g. an exchange tick/step).

    Defaults to ROUND_DOWN — for order sizes we never want to round *up* past a limit.
    """
    v = D(value)
    inc = D(increment)
    if inc <= 0:
        return v
    return (v / inc).to_integral_value(rounding=rounding) * inc


def money(value: Number, places: int = 2) -> Decimal:
    """Quantize to a fixed number of decimal places (default cents), half-up."""
    q = Decimal(1).scaleb(-places)
    return D(value).quantize(q, rounding=ROUND_HALF_UP)


def pct_of(value: Number, percent: Number) -> Decimal:
    """`percent` percent of `value` (e.g. pct_of(200, 10) == 20)."""
    return D(value) * D(percent) / Decimal(100)


def clamp(value: Number, low: Number, high: Number) -> Decimal:
    """Constrain value to the inclusive [low, high] range."""
    v = D(value)
    return max(D(low), min(v, D(high)))


def is_positive(value: Number) -> bool:
    return D(value) > ZERO
