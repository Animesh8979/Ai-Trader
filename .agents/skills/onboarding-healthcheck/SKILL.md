---
name: "Onboarding Healthcheck"
description: "Runs setup wizards, smoke tests, and environment diagnostics."
---
# Onboarding Healthcheck Skill

This skill governs system onboarding, credentials validation, and sandbox smoke test execution.

## Healthcheck Steps
1. **Setup Wizard**: Run `python scripts/setup_wizard.py` to configure folders, `.env`, and config paths.
2. **Smoke Test**: Run `python scripts/smoke_test.py` to verify API links, SQLite records, and model availability.
3. **Diagnostics Report**: Query active configuration parameters and print summary tables.
