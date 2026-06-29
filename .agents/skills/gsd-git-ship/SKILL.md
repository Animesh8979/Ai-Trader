---
name: "GSD Git Ship"
description: "Automates committing, pushing, and merging code changes safely using Git."
---
# GSD Git Ship Skill

This skill governs the Git commit and push pipeline to ensure clean, reviewable, and version-controlled history.

## shipping Protocol
1. **Inspect Status**: Check modified files using `git status` and `git diff` before adding changes.
2. **Structured Commits**: Commit changes using explicit conventional commits format (e.g. `feat(dashboard): ...` or `fix(risk): ...`).
3. **Push & Track**: Push to origin remote and track build states or test actions.
