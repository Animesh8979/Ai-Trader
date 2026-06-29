---
name: blackboard-negotiation
description: Protocol for Bull vs Bear agents to safely read/write to the shared Network-AI blackboard.
---

# Blackboard Negotiation

When interacting with the `network_ai` MCP server:
1. **Always acquire a lock:** Before updating a state machine transition on the blackboard, assert that you hold the lock for the current block.
2. **Post atomic updates:** Write JSON payloads containing your analysis. Do not write unstructured text.
3. **Respect budget constraints:** Only spawn sub-agents if the budget tracking on the blackboard shows positive remaining tokens.
