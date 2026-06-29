---
name: "GSD Context Hygiene"
description: "Manages and preserves agent context size by cleaning chat threads and session state."
---
# GSD Context Hygiene Skill

This skill helps maintain clean agent context windows to prevent performance degradation ("context rot") as conversations grow.

## Hygiene Rules
1. **Isolate Tasks**: Spawn lightweight, specialized subagents for distinct research or debugging tasks using `invoke_subagent`.
2. **Clean Output**: Limit command log outputs (e.g., git log, test tracebacks) using paging flags (e.g. `git log -n 5` or `pytest -q`).
3. **Volatile Storage**: Avoid reading large database dumps or binaries directly. Query them with specific limits or grep filters.
