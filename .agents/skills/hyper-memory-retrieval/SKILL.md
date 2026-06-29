---
name: hyper-memory-retrieval
description: Using PG-Mnemosyne to retrieve historical backtest performance during live runs.
---

# Hyper Memory Retrieval

When utilizing the `pg_mnemosyne` MCP server:
1. **Semantic Search:** Use semantic queries to find similar past market conditions (e.g., "Find times when BTC dropped 5% in 1 hour while SPY was flat").
2. **Tagging:** Always append relevant tags (e.g., `#black_swan`, `#flash_crash`) when saving new memories.
3. **Context Truncation:** Request memories in summaries rather than full JSON logs to prevent token overflow.
