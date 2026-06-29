---
name: "GSD Quality Audit"
description: "Guides code reviews to identify concurrency leaks, security risks, and error handlers."
---
# GSD Quality Audit Skill

This skill governs codebase audits to enforce safety, security, and concurrency hygiene.

## Audit Checklist
1. **Concurrency**: Verify thread pools (ThreadPoolExecutor) do not cause deadlock or leak file descriptors.
2. **Error Handling**: Ensure try-catch loops in async event loops do not swallow exceptions silently.
3. **Secrets Isolation**: Confirm API credentials (Binance/Finnhub keys) are never logged or hardcoded.
