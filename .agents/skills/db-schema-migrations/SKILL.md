---
name: "DB Schema Migrations"
description: "Creates, checks, and migrates SQLite schemas for orders, fills, and decisions."
---
# DB Schema Migrations Skill

This skill governs schema management for the local SQLite database (`data/godmode.db`).

## Migration Steps
1. **Backup**: Copy the active SQLite db file before executing schema upgrades.
2. **Structured Tables**: Define tables for `orders`, `fills`, `decisions`, `agent_messages`, and `kill_events` with explicit types and indexes.
3. **Idempotence**: Write migration scripts containing `IF NOT EXISTS` flags to prevent execution crashes.
