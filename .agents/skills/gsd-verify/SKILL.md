---
name: "GSD Verify"
description: "Guides the verify phase of GSD workflow to execute test suites and verify outputs."
---
# GSD Verify Skill

This skill governs the verification phase of the Get Shit Done workflow. It guarantees all implemented changes have the desired effects and do not introduce regressions.

## Verification Protocol
1. **Automated Unit Tests**: Execute the full pytest suite using the project virtual environment launcher:
   `poetry run pytest` or `.venv\Scripts\pytest.exe`
2. **Sandbox Execution**: Run local sandbox test harnesses (e.g., `python scripts/sandbox_test.py`) to confirm execution loops finish without hanging or memory leaks.
3. **Log Audit**: Check SQLite decisions and metrics database tables to confirm transactions are logged correctly.
