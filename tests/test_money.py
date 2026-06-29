from decimal import Decimal

from godmode.core.money import D, clamp, is_positive, money, pct_of, quantize


def test_D_converts_float_via_str():
    assert D(0.1) == Decimal("0.1")          # not 0.1000000000000000055...
    assert D("1.23") == Decimal("1.23")
    assert D(5) == Decimal("5")


def test_quantize_rounds_down_to_increment():
    assert quantize("1.2345", "0.01") == Decimal("1.23")
    assert quantize("0.000223", "0.00001") == Decimal("0.00022")
    assert quantize("10", "0") == Decimal("10")  # zero increment -> unchanged


def test_money_fixed_places_half_up():
    assert money("1.005", 2) == Decimal("1.01")
    assert money(2, 2) == Decimal("2.00")


def test_pct_of():
    assert pct_of(200, 10) == Decimal("20")
    assert pct_of("50", "0.5") == Decimal("0.25")


def test_clamp():
    assert clamp(5, 0, 10) == Decimal("5")
    assert clamp(-1, 0, 10) == Decimal("0")
    assert clamp(99, 0, 10) == Decimal("10")


def test_is_positive():
    assert is_positive("0.0001")
    assert not is_positive(0)
    assert not is_positive("-1")
