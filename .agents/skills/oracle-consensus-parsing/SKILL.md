---
name: oracle-consensus-parsing
description: Rules for aggregating the 11 signals from Octodamus without hallucination.
---

# Oracle Consensus Parsing

When using the `octodamus` MCP server, you MUST strictly adhere to the following parsing rules to prevent hallucinating false buy/sell signals:
1. **Never average the signals manually:** The oracle provides a deterministic `consensus_score`. Use it.
2. **Require 8/11 Confluence:** A trade execution is only valid if 8 out of the 11 sub-signals align in the same direction.
3. **Verify On-Chain Signature:** Check the Ed25519 signature returned by the tool to ensure the data has not been tampered with.
