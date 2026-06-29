---
name: dynamic-infrastructure-scaling
description: Agentic deployment of new Docker containers when load increases.
---

# Dynamic Infrastructure Scaling

When interacting with the `agentdeals` or `docker` MCP servers:
1. **Cost Comparison:** Use `agentdeals` to find the cheapest spot instances before deploying heavy compute containers.
2. **Automated Teardown:** Ensure any dynamically spawned Docker container has a strict TTL (Time To Live) or auto-destruct sequence to prevent zombie instances.
3. **Stateless execution:** Only spawn stateless workers; all state must reside in the Postgres ledger or PG-Mnemosyne.
