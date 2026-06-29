---
name: autonomous-bounty-hiring
description: Logic for using Swarmwage to request external compute/data.
---

# Autonomous Bounty Hiring

When the system cannot solve a task internally and invokes the `swarmwage` MCP server:
1. **Define precise JSON schemas:** Specify exactly what the hired agent must return.
2. **Maximum Bounty Limit:** Never authorize a payment greater than $5 USDC per task.
3. **Wait for Settlement:** Do not proceed with execution until the Swarmwage tool returns the on-chain receipt (EIP-3009).
