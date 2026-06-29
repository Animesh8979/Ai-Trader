---
name: macro-sec-filing-analysis
description: Event-driven analysis on live SEC data via Katzilla.
---

# Macro SEC Filing Analysis

When querying the `katzilla` MCP server for macroeconomic or SEC data:
1. **Prioritize 8-K and 13F filings:** These contain the most market-moving data.
2. **Extract structured JSON:** Do not read raw HTML of SEC filings. Use the Katzilla parsing tool to extract the JSON payload containing the CUSIP, Shares, and Value.
3. **Correlate with FRED:** Cross-reference any major sector shifts against the current BLS/FRED inflation metrics provided by Katzilla.
