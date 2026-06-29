---
name: "Parallel Agent Debate"
description: "Orchestrates multi-agent debates concurrently using thread pools to optimize latency."
---
# Parallel Agent Debate Skill

This skill governs the concurrent dispatch of LLM prompts for debate agents to minimize trading loop latency.

## Orchestration Guidelines
1. **Thread Isolation**: Dispatch non-dependent agent prompts (e.g. Bullish Researcher and Bearish Researcher) inside a `ThreadPoolExecutor` block.
2. **Latency Budget**: Limit LLM response timeouts to 15 seconds to prevent execution loop delays.
3. **Consensus Aggregation**: Combine debate logs into a single structured payload for the Trader and Risk agents.
