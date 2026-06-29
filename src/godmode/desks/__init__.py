"""Per-market desks (Phase 2+).

Each desk (crypto, prediction markets, equities, fx) owns its venue adapter and a set of
market-specific sub-agents, coordinated by a top-level Portfolio Orchestrator that
allocates capital/attention across desks and enforces portfolio-wide risk.
"""
