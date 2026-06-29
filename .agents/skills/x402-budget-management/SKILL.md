---
name: x402-budget-management
description: Strict limits on how much USDC the agents can spend per day on dynamic APIs.
---

# x402 Budget Management

When using the `x402station` MCP server to discover new APIs:
1. **Daily Cap:** Do not exceed $10.00 USDC in total API spend per 24-hour period.
2. **Trust Score:** Only execute endpoints that have an `x402_trust_score` greater than 80.
3. **Preflight Checks:** Always run the `preflight` tool before committing to a paid endpoint to ensure it is not a decoy or dead service.
