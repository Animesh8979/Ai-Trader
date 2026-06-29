"""Godmode Trading Agent.

A precise, automated, reliable multi-agent autonomous trading system.

Design priorities (in order): correctness, survivability, discipline — then returns.
The LLM *proposes*; the deterministic risk engine *disposes*. Paper-first, always.

Architecture layers (see the package layout):
    core        - config, logging, money math, sqlite, audit log, kill switch
    llm         - model-agnostic LLM layer (Claude / Gemini / OpenAI / Ollama via LiteLLM)
    data        - market data, news, sentiment providers
    strategies  - deterministic quant strategies (the substrate)
    risk        - the inviolable deterministic risk engine + circuit breakers
    execution   - venue adapters + (Phase 1) NautilusTrader integration + reconciliation
    agents      - orchestrator + narrow-role sub-agents (analyst/bull/bear/trader/risk/reflection)
    desks       - per-market desks (crypto, prediction, equities, fx)
    backtest    - backtest harness, metrics, reports
    dashboard   - local web UI (live PnL, positions, agent reasoning, STOP button)
"""

__version__ = "0.1.0"
__all__ = ["__version__"]
