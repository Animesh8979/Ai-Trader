from decimal import Decimal

from godmode.core.config import RiskLimits
from godmode.risk import OrderProposal, PortfolioState, RiskEngine, Verdict


def _limits(**over) -> RiskLimits:
    base = dict(
        max_position_pct=10.0,
        max_total_exposure_pct=60.0,
        max_daily_loss_pct=3.0,
        max_drawdown_pct=15.0,
        max_consecutive_losses=6,
        per_order_max_notional=5000.0,
        min_order_notional=10.0,
        max_open_positions=8,
    )
    base.update(over)
    return RiskLimits(**base)


def _engine(**over) -> RiskEngine:
    return RiskEngine(limits=_limits(**over))


def _portfolio(**over) -> PortfolioState:
    base = dict(equity="100000")
    base.update(over)
    return PortfolioState(**base)


# --- happy path --------------------------------------------------------------
def test_approve_within_limits():
    # $5000 notional, 5% of equity, within all limits
    d = _engine().evaluate(
        OrderProposal("BTC/USDT", "buy", qty="0.1", price="50000"), _portfolio()
    )
    assert d.verdict == Verdict.APPROVE
    assert d.approved_qty == Decimal("0.1")


# --- sizing clamps -----------------------------------------------------------
def test_clamp_per_order_notional():
    # per-order cap $5000; propose $20000 -> clamp down
    d = _engine(max_position_pct=100.0).evaluate(
        OrderProposal("BTC/USDT", "buy", qty="0.4", price="50000"), _portfolio()
    )
    assert d.verdict == Verdict.CLAMP
    assert d.approved_notional(Decimal("50000")) <= Decimal("5000.0001")


def test_clamp_max_position_pct():
    # position cap 2% of 100k = $2000; per-order cap high so position cap binds
    d = _engine(max_position_pct=2.0, per_order_max_notional=1_000_000).evaluate(
        OrderProposal("BTC/USDT", "buy", qty="1", price="50000"), _portfolio()
    )
    assert d.verdict == Verdict.CLAMP
    assert d.approved_notional(Decimal("50000")) <= Decimal("2000.0001")


def test_clamp_to_remaining_exposure():
    # exposure cap 60% of 100k = 60k; already 58k used -> only 2k headroom
    d = _engine(per_order_max_notional=1_000_000, max_position_pct=100.0).evaluate(
        OrderProposal("ETH/USDT", "buy", qty="1", price="50000"),
        _portfolio(gross_exposure="58000"),
    )
    assert d.verdict == Verdict.CLAMP
    assert d.approved_notional(Decimal("50000")) <= Decimal("2000.0001")


# --- rejections --------------------------------------------------------------
def test_reject_dust_order():
    d = _engine().evaluate(
        OrderProposal("BTC/USDT", "buy", qty="0.0001", price="50"), _portfolio()
    )  # $5 notional < $10 min
    assert d.verdict == Verdict.REJECT


def test_reject_non_positive():
    d = _engine().evaluate(OrderProposal("BTC/USDT", "buy", qty="0", price="50000"), _portfolio())
    assert d.verdict == Verdict.REJECT


def test_reject_max_open_positions_for_new_symbol():
    d = _engine(max_open_positions=3).evaluate(
        OrderProposal("NEW/USDT", "buy", qty="0.01", price="50000"),
        _portfolio(open_positions=3, has_position_in_symbol=False),
    )
    assert d.verdict == Verdict.REJECT
    assert "max_open_positions" in d.breakers


def test_reject_exhausted_exposure():
    d = _engine().evaluate(
        OrderProposal("ETH/USDT", "buy", qty="1", price="50000"),
        _portfolio(gross_exposure="60000"),  # exactly at the 60% cap
    )
    assert d.verdict == Verdict.REJECT
    assert "max_total_exposure" in d.breakers


# --- circuit breakers --------------------------------------------------------
def test_daily_loss_blocks_new_entries():
    d = _engine().evaluate(
        OrderProposal("BTC/USDT", "buy", qty="0.01", price="50000"),
        _portfolio(day_realized_pnl="-3500"),  # lost 3.5% > 3% limit
    )
    assert d.verdict == Verdict.REJECT
    assert "daily_loss" in d.breakers
    assert d.should_halt is False  # soft, time-based — not a full kill


def test_consecutive_losses_cooldown():
    d = _engine().evaluate(
        OrderProposal("BTC/USDT", "buy", qty="0.01", price="50000"),
        _portfolio(consecutive_losses=6),
    )
    assert d.verdict == Verdict.REJECT
    assert "consecutive_losses" in d.breakers


def test_drawdown_triggers_hard_halt():
    d = _engine().evaluate(
        OrderProposal("BTC/USDT", "buy", qty="0.01", price="50000"),
        _portfolio(equity="80000", peak_equity="100000"),  # 20% dd > 15% limit
    )
    assert d.verdict == Verdict.REJECT
    assert d.should_halt is True
    assert "max_drawdown" in d.breakers


# --- reducing orders bypass entry gates --------------------------------------
def test_reducing_order_bypasses_daily_loss():
    d = _engine().evaluate(
        OrderProposal("BTC/USDT", "sell", qty="0.01", price="50000", is_reducing=True),
        _portfolio(day_realized_pnl="-9000", consecutive_losses=10),
    )
    assert d.verdict == Verdict.APPROVE  # you can always cut risk


def test_reducing_order_still_blocked_by_hard_drawdown():
    # Hard drawdown halt applies even to reducing orders (full stop).
    d = _engine().evaluate(
        OrderProposal("BTC/USDT", "sell", qty="0.01", price="50000", is_reducing=True),
        _portfolio(equity="80000", peak_equity="100000"),
    )
    assert d.verdict == Verdict.REJECT
    assert d.should_halt is True
