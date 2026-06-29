"""Multi-agent brain (Phase 2).

A TradingAgents-style pipeline of narrow-role sub-agents — analysts gather facts, a
bull and a bear debate them, a trader proposes one concrete action, and a risk-manager
agent critiques it. Each sub-agent has a tight scope and its own context, which is what
keeps the system from getting lost or hallucinating. The LLM output is only a *proposal*;
it must still pass the deterministic risk engine before anything executes.
"""

from godmode.agents.brain import MultiAgentBrain

__all__ = ["MultiAgentBrain"]

