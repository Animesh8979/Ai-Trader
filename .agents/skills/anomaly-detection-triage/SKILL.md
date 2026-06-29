---
name: anomaly-detection-triage
description: Auto-halting the KillSwitch if Aegis-DQ detects a corrupt database row.
---

# Anomaly Detection Triage

If the `aegis_dq` MCP server reports a Data Quality failure:
1. **Halt execution immediately:** Engage the global `KillSwitch`.
2. **LLM Root Cause Analysis:** Request the `aegis_dq` tool to run its LLM-based root cause analysis on the failing rows.
3. **No manual remediation:** Do not attempt to manually execute `UPDATE` or `DELETE` statements on the Postgres ledger. Log the failure and await human intervention.
