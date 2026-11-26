"""Ai-Trader — paper-first quantitative risk, regime-detection, and execution engine.

Design priorities (in order): correctness, survivability, discipline — then returns.
The LLM *proposes*; the deterministic risk engine *disposes*. Paper-first by default.

Architecture layers (see the package layout):
    core        - config, logging, money math, sqlite, audit log, kill switch
    llm         - model-agnostic LLM layer (Claude / Gemini / OpenAI / Ollama via LiteLLM)
    data        - market data, news, sentiment providers
    strategies  - deterministic quant strategies & regime filters
    risk        - deterministic risk engine, Cornish-Fisher VaR, Welford OFI veto, circuit breakers
    execution   - venue adapters (CCXT testnet & Shoonya paper/sandbox), live runner, reconciliation
    agents      - orchestrator + narrow-role sub-agents (analyst/bull/bear/trader/risk/reflection)
    desks       - per-market desks
    backtest    - deterministic CSV backtest harness & metrics
    dashboard   - FastAPI + WebSocket local telemetry UI and kill-switch control
"""

__version__ = "0.1.0"
__all__ = ["__version__"]
