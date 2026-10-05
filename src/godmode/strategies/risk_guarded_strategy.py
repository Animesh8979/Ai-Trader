"""The Nautilus execution wrapper that makes risk enforcement non-bypassable.

Every order passes through two gates before reaching the venue: the physical
kill switch (the data/STOP sentinel file) and the deterministic RiskEngine
(clamp/reject). The base class's `submit_order` is only invoked for APPROVE and
CLAMP verdicts — a REJECT never leaves this process.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from nautilus_trader.trading.strategy import Strategy, StrategyConfig

from godmode.core.logging import get_logger
from godmode.risk.engine import OrderProposal, PortfolioState, RiskEngine, Verdict

log = get_logger("strategy.risk_guarded")

_FALLBACK_EQUITY = 100_000.0


def _to_decimal(value: Any) -> Decimal:
    try:
        parsed = Decimal(str(value))
        return parsed if parsed.is_finite() else Decimal(0)
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(0)


class RiskGuardedStrategyConfig(StrategyConfig):
    def __init__(self, instrument_id: str = "BTCUSDT.BINANCE", **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.instrument_id = instrument_id


class RiskGuardedStrategy(Strategy):
    """Wraps any Nautilus strategy flow so orders cannot bypass the risk layer."""

    def __init__(self, config: Any) -> None:
        super().__init__(config)
        self.config = config
        self.kill_switch = None
        self.risk_engine = RiskEngine()
        try:
            from godmode.core.killswitch import get_kill_switch

            self.kill_switch = get_kill_switch()
        except Exception as exc:
            log.warning(f"kill switch unavailable at init: {exc}")

    # ------------------------------------------------------------------ #
    #  Order gate
    # ------------------------------------------------------------------ #
    def submit_order(self, order, position_id=None, client_id=None, params=None):
        instrument = order.instrument_id

        if self.kill_switch is not None and self.kill_switch.is_halted():
            self.log.error(f"BLOCKED order for {instrument}: kill switch is engaged.")
            return

        proposal = self._proposal_from(order)
        portfolio = self._portfolio_snapshot()
        decision = self.risk_engine.evaluate_and_enforce(
            proposal, portfolio, kill_switch=self.kill_switch
        )

        if decision.verdict == Verdict.REJECT or decision.approved_qty <= 0:
            reasons = ", ".join(decision.reasons) or "no reason given"
            self.log.error(f"REJECTED order for {instrument}: {reasons}")
            return

        if decision.verdict == Verdict.CLAMP:
            order.quantity = self._quantity_for(order, decision.approved_qty)
            self.log.warning(
                f"CLAMPED order for {instrument} to {decision.approved_qty}: "
                f"{', '.join(decision.reasons)}"
            )
        else:
            self.log.info(f"APPROVED order for {instrument}: {', '.join(decision.reasons)}")

        super().submit_order(order, position_id=position_id, client_id=client_id, params=params)

    # ------------------------------------------------------------------ #
    #  Context builders
    # ------------------------------------------------------------------ #
    def _proposal_from(self, order) -> OrderProposal:
        raw_side = getattr(order.side, "name", None) or str(order.side)
        side = "buy" if "BUY" in str(raw_side).upper() else "sell"
        ident = str(order.instrument_id)
        venue, _, symbol = ident.rpartition(".")
        if not venue:
            venue, symbol = "", ident
        current_pos = 0.0
        try:
            pos = self.portfolio.get_position(order.instrument_id)
            if pos is not None:
                current_pos = float(pos.quantity)
        except Exception:
            pass
            
        is_reducing = False
        if side == "sell" and current_pos > 0:
            is_reducing = True
        elif side == "buy" and current_pos < 0:
            is_reducing = True

        return OrderProposal(
            symbol=symbol,
            side=side,
            qty=_to_decimal(getattr(order, "quantity", None)),
            price=_to_decimal(getattr(order, "price", None)),
            venue=venue,
            is_reducing=is_reducing,
        )

    def _portfolio_snapshot(self) -> PortfolioState:
        """Best-effort account snapshot; falls back to paper equity offline."""
        equity = Decimal(str(_FALLBACK_EQUITY))
        try:
            from godmode.core.config import load_config

            equity = D(load_config().app.paper_starting_equity)
        except Exception:
            pass
        try:
            accounts = dict(self.portfolio.accounts).values()
            total = sum(float(acc.balance_total.as_double()) for acc in accounts)
            if total > 0:
                equity = Decimal(str(total))
        except Exception:
            pass
        return PortfolioState(equity=equity)

    def _quantity_for(self, order, approved: Decimal):
        target = float(approved)
        precision = getattr(order.quantity, "precision", 8)
        try:
            from nautilus_trader.model.objects import Quantity

            return Quantity(target, int(precision))
        except Exception:
            return target
