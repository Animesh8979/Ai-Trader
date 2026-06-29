## BEGIN MANAGED BLOCK: shared-project-brain
# Shared Project Brain

> [!CAUTION]
> **GLOBAL PERSONA DIRECTIVE**
> Before executing ANY command, you MUST read and strictly adhere to D:\AgentBrains\MASTER_PROMPT.md. You act as the Autonomous Staff Systems Architect. Do not deviate.

Project: AI Trader
Source: D:\Ai trader
Brain: D:\AgentBrains\projects\ai-trader
Registry: D:\AgentBrains\agent-brain-registry.json
Graph: D:\AgentBrains\projects\ai-trader\graphify-out\graph.json

Rules:
1. Query this project's graph before broad file reads or searches.
2. Keep this project brain separate from the other two project brains.
3. Do not ingest secrets, credentials, databases, binary media, browser caches, or generated dependencies.
4. After meaningful work, append a short entry to D:\AgentBrains\projects\ai-trader\logs\activity.md.

Commands:
- Build/update: D:\AgentBrains\tools\agent-brain.ps1 -Action build -Project ai-trader
- Query: D:\AgentBrains\tools\agent-brain.ps1 -Action query -Project ai-trader -Question "your question"
- Status: D:\AgentBrains\tools\agent-brain.ps1 -Action status -Project ai-trader
## END MANAGED BLOCK: shared-project-brain

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).

