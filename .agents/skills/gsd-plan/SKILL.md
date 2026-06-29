---
name: "GSD Plan"
description: "Guides the plan phase of GSD workflow to write implementation plans and task lists."
---
# GSD Plan Skill

This skill governs the planning phase of the Get Shit Done workflow. It transforms alignment from the discuss phase into a concrete, spec-driven blueprint before any modifying code changes are applied.

## Planning Protocol
1. **Define Goals**: Clearly explain the target outcome and what is considered a verified success.
2. **Draft task.md**: Lay out a checkable task checklist (using `- [ ]` format) mapping items to component levels.
3. **Draft implementation_plan.md**: Group changes logically by components. Order dependencies first. Use `[MODIFY]`, `[NEW]`, and `[DELETE]` tags next to file paths.
4. **Write Verification Plan**: Define explicit automated commands (`pytest`) and manual verification steps (UI validations) to test the implementation.
