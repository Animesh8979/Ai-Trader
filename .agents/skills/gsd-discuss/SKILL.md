---
name: "GSD Discuss"
description: "Guides the discuss phase of Get Shit Done (GSD) workflow to align on requirements and trade-offs."
---
# GSD Discuss Skill

This skill governs the initial phase of the Get Shit Done workflow. The goal is to establish shared alignment, collect requirements, identify system boundaries, and surface any design constraints before writing code or plans.

## Workflow Protocol
1. **Clarify Intent**: Restate the user's request in first-principles terms. Identify what visual, mathematical, or operational parameters are requested.
2. **Surface Constraints**: Call out system limits, dependencies, API limits (e.g. Binance weight caps, Nvidia rate limits), and target configurations.
3. **Verify Pre-conditions**: Inspect current codebase configurations (e.g. SQLite schema, environment variables) to establish the baseline state.
4. **Identify Trade-offs**: Discuss architectural trade-offs (e.g., synchronous thread blocking vs asynchronous loop scheduling).
