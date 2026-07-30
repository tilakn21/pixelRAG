# Claude Code Specific Rules

This file contains overrides and specific instructions for Claude Code. These rules build upon the shared instructions in `AGENTS.md`.

## 1. File Editing
- Be precise when making large file edits. Always use search-and-replace effectively to avoid replacing entire files if a smaller, more targeted edit is possible.
- Pay close attention to indentation and whitespace, particularly in Python files.

## 2. Command Execution
- Do not run potentially destructive commands (e.g., `rm -rf`, dropping tables) without explicit confirmation from the user.
- Prefer running tests and linting automatically after making significant logic changes to verify your own work.

## 3. Communication
- Refrain from providing overly verbose explanations for straightforward code changes.
- If a task involves multiple distinct steps, briefly explain your strategy before beginning.
