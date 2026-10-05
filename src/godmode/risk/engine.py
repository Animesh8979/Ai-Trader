"""The deterministic risk engine — the inviolable guard.

Pure Python, no LLM, no I/O (except an optional kill-switch side effect). Every proposed
order is evaluated against hard limits and circuit breakers. The engine can APPROVE a
proposal, CLAMP it down to a safe size, or REJECT it outright. The LLM cannot override it.

Two classes of control:
  * Sizing limits (per-order notional, max position %, total exposure) -> CLAMP toward safe.
  * Circuit breakers (drawdown, daily loss, consecutive losses, max positions) -> REJECT,
    and the hard ones (drawdown, equity<=0) also signal a full halt.

Risk-*reducing* orders (closing/trimming a position) bypass the entry gates so you can
always cut risk, even while halted on entries.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Optional

from godmode.core.config import RiskLimits, load_config
from godmode.core.logging import get_logger
from godmode.core.money import D, ZERO, pct_of

log = get_logger("risk")


class Verdict(str, Enum):
    APPROVE = "approve"
    CLAMP = "clamp"
    REJECT = "reject"


@dataclass
class OrderProposal:
    """A proposed order coming from a strategy or the LLM brain."""

    symbol: str
    side: str               # "buy" | "sell"
    qty: Decimal
    price: Decimal          # limit price, or current mark for market orders (> 0)
    venue: str = ""
    order_type: str = "limit"
    is_reducing: bool = False  # True if this trims/closes an existing position

    def __post_init__(self) -> None:
        self.qty = D(self.qty)
        self.price = D(self.price)

    @property
    def notional(self) -> Decimal:
        return (self.qty * self.price).copy_abs()


@dataclass
class PortfolioState:
    """Snapshot of the account at decision time."""

    equity: Decimal
    peak_equity: Optional[Decimal] = None
    day_realized_pnl: Decimal = ZERO       # negative when losing on the day
    gross_exposure: Decimal = ZERO         # sum of |position notional| currently open
    open_positions: int = 0
    consecutive_losses: int = 0
    has_position_in_symbol: bool = False   # already hold the proposal's symbol?
    historical_returns: Optional[list[float]] = None  # empirical portfolio returns for VaR models

    def __post_init__(self) -> None:
        self.equity = D(self.equity)
        self.peak_equity = D(self.peak_equity) if self.peak_equity is not None else self.equity
        self.day_realized_pnl = D(self.day_realized_pnl)
        self.gross_exposure = D(self.gross_exposure)


@dataclass
class RiskDecision:
    verdict: Verdict
    approved_qty: Decimal
    reasons: list[str] = field(default_factory=list)
    breakers: list[str] = field(default_factory=list)
    should_halt: bool = False
    halt_reason: Optional[str] = None

    @property
    def approved(self) -> bool:
        return self.verdict in (Verdict.APPROVE, Verdict.CLAMP) and self.approved_qty > 0

    def approved_notional(self, price: Decimal) -> Decimal:
        return (self.approved_qty * D(price)).copy_abs()


class RiskEngine:
    def __init__(self, limits: Optional[RiskLimits] = None):
        self.limits = limits or load_config().risk

    # ------------------------------------------------------------------ #
    #  Pure evaluation (no side effects) — fully unit-testable
    # ------------------------------------------------------------------ #
    def evaluate(self, proposal: OrderProposal, portfolio: PortfolioState) -> RiskDecision:
        L = self.limits
        qty, price, equity = proposal.qty, proposal.price, portfolio.equity
        reasons: list[str] = []
        breakers: list[str] = []

        # --- 0) basic sanity -------------------------------------------------
        if qty <= 0 or price <= 0:
            return RiskDecision(Verdict.REJECT, ZERO, ["non-positive qty or price"])
        if proposal.side not in ("buy", "sell"):
            return RiskDecision(Verdict.REJECT, ZERO, [f"unknown side '{proposal.side}'"])
        if equity <= 0:
            return RiskDecision(
                Verdict.REJECT, ZERO, ["equity <= 0"],
                should_halt=True, halt_reason="equity depleted (<= 0)",
            )

        # --- 1) hard circuit breaker: max drawdown (applies to ALL orders) ---
        dd_floor = portfolio.peak_equity * (D(1) - D(L.max_drawdown_pct) / D(100))
        if equity <= dd_floor:
            breakers.append("max_drawdown")
            return RiskDecision(
                Verdict.REJECT, ZERO,
                [f"max drawdown breached: equity {equity} <= floor {dd_floor}"],
                breakers=breakers, should_halt=True,
                halt_reason=f"max drawdown {L.max_drawdown_pct}% breached",
            )

        # --- 2) entry gates (skipped for risk-reducing orders) ---------------
        if not proposal.is_reducing:
            loss = -portfolio.day_realized_pnl  # positive magnitude when losing
            if loss >= pct_of(equity, L.max_daily_loss_pct):
                breakers.append("daily_loss")
                return RiskDecision(
                    Verdict.REJECT, ZERO,
                    [f"daily loss limit hit: lost {loss} >= {L.max_daily_loss_pct}% of equity"],
                    breakers=breakers,
                )

            if portfolio.consecutive_losses >= L.max_consecutive_losses:
                breakers.append("consecutive_losses")
                return RiskDecision(
                    Verdict.REJECT, ZERO,
                    [f"{portfolio.consecutive_losses} consecutive losses >= "
                     f"limit {L.max_consecutive_losses}; cooling down"],
                    breakers=breakers,
                )

            if not portfolio.has_position_in_symbol and portfolio.open_positions >= L.max_open_positions:
                breakers.append("max_open_positions")
                return RiskDecision(
                    Verdict.REJECT, ZERO,
                    [f"already at max open positions ({L.max_open_positions})"],
                    breakers=breakers,
                )

            if portfolio.historical_returns and len(portfolio.historical_returns) >= 30:
                from godmode.risk.var_models import cornish_fisher_var

                var_val = cornish_fisher_var(portfolio.historical_returns, confidence_level=0.99)
                var_pct = var_val * 100.0
                if var_pct >= L.var_limit_pct:
                    breakers.append("portfolio_var_limit")
                    return RiskDecision(
                        Verdict.REJECT, ZERO,
                        [f"portfolio VaR(99%) {var_pct:.2f}% breaches limit {L.var_limit_pct:.2f}%"],
                        breakers=breakers,
                    )

        # --- 3) sizing clamps (entry orders only) ----------------------------
        verdict = Verdict.APPROVE
        approved_qty = qty

        if not proposal.is_reducing:
            # per-order max notional
            per_order_cap = D(L.per_order_max_notional)
            if approved_qty * price > per_order_cap:
                approved_qty = per_order_cap / price
                verdict = Verdict.CLAMP
                reasons.append(f"clamped to per-order max notional {per_order_cap}")

            # per-position cap (% of equity)
            pos_cap = pct_of(equity, L.max_position_pct)
            if approved_qty * price > pos_cap:
                approved_qty = pos_cap / price
                verdict = Verdict.CLAMP
                reasons.append(f"clamped to max position {L.max_position_pct}% of equity ({pos_cap})")

            # total exposure budget
            exposure_cap = pct_of(equity, L.max_total_exposure_pct)
            remaining = exposure_cap - portfolio.gross_exposure
            if remaining <= 0:
                breakers.append("max_total_exposure")
                return RiskDecision(
                    Verdict.REJECT, ZERO,
                    reasons + [f"no exposure budget left (cap {exposure_cap}, used {portfolio.gross_exposure})"],
                    breakers=breakers,
                )
            if approved_qty * price > remaining:
                approved_qty = remaining / price
                verdict = Verdict.CLAMP
                reasons.append(f"clamped to remaining exposure budget {remaining}")

        # --- 4) dust check (entry orders only; reducing closes are allowed) --
        if not proposal.is_reducing and approved_qty * price < D(L.min_order_notional):
            return RiskDecision(
                Verdict.REJECT, ZERO,
                reasons + [f"order notional {approved_qty * price} below minimum {L.min_order_notional}"],
                breakers=breakers,
            )

        if approved_qty <= 0:
            return RiskDecision(Verdict.REJECT, ZERO, reasons + ["clamped to zero"], breakers=breakers)

        if not reasons:
            reasons.append("within all risk limits")
        return RiskDecision(verdict, approved_qty, reasons=reasons, breakers=breakers)

    # ------------------------------------------------------------------ #
    #  Enforcement wrapper (applies the kill-switch side effect)
    # ------------------------------------------------------------------ #
    def evaluate_and_enforce(
        self, proposal: OrderProposal, portfolio: PortfolioState, kill_switch=None
    ) -> RiskDecision:
        decision = self.evaluate(proposal, portfolio)
        if decision.should_halt:
            ks = kill_switch
            if ks is None:
                from godmode.core.killswitch import get_kill_switch

                ks = get_kill_switch()
            ks.engage(decision.halt_reason or "risk engine hard halt", source="risk_engine")
            log.error(f"RISK HALT: {decision.halt_reason}")
        return decision
