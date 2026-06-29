"""The deterministic risk engine (Phase 1) — the "godmode" guard.

Pure Python, no LLM. Every proposed order passes through hard pre-trade checks
(position caps, exposure limits, daily-loss limit, max drawdown, order sanity) and
portfolio circuit breakers. The engine can shrink an order, reject it, or approve it —
and the LLM can never override it. This is the layer that makes any edge survivable.
"""

from godmode.risk.engine import (  # noqa: F401
    OrderProposal,
    PortfolioState,
    RiskDecision,
    RiskEngine,
    Verdict,
)

__all__ = ["OrderProposal", "PortfolioState", "RiskDecision", "RiskEngine", "Verdict"]
