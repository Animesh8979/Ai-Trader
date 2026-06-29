---
name: "GSD Execute"
description: "Guides the execute phase of GSD workflow to apply changes cleanly without stubs."
---
# GSD Execute Skill

This skill governs the execution phase of the Get Shit Done workflow. It enforces clean, production-ready coding practices, structural hygiene, and zero-slop edits.

## Execution Rules
1. **Zero Placeholder Code**: Never emit code containing `// TODO` or `pass` placeholders. All code blocks must be fully implemented, compilable, and production-ready.
2. **Incremental Edits**: Apply code changes incrementally using exact replace chunk tools (`replace_file_content` or `multi_replace_file_content`).
3. **Preserve Context**: Maintain all original comments, docstrings, and headers unless explicitly requested to alter them.
4. **Clean Workspaces**: Ensure all temporary scratch files are isolated in the conversation scratch directories, leaving the main repo root clean.
