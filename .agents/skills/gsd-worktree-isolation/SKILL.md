---
name: "GSD Worktree Isolation"
description: "Manages Git worktree operations to isolate development tasks and maintain clean checkouts."
---
# GSD Worktree Isolation Skill

This skill governs the use of Git worktrees to isolate concurrent tasks, prevent merge conflicts, and preserve main checkout integrity.

## Worktree Guidelines
1. **Creation**: Mount fresh worktrees for new branches inside sandbox folders using:
   `git worktree add <path> <branch>`
2. **Execution**: Perform all modifying compiles and tests within the worktree boundaries.
3. **Cleanup**: Remove the worktree mount and prune state after shipping changes:
   `git worktree remove <path>` and `git worktree prune`
