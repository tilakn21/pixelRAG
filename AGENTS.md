# Shared Agent Rules

This file contains shared instructions and guidelines that ALL AI agents (Gemini, Claude, etc.) must follow when working in this repository.

## 1. General Behavior
- **Understand Before Modifying**: Never make sweeping changes without understanding the surrounding context. Read relevant files first.
- **Keep It Concise**: Do not output large blocks of text or explanations unless explicitly requested. Keep summaries brief.
- **Ask Clarifying Questions**: If requirements are ambiguous, ask the user instead of making guesses that could lead to extensive rework.
- **Verify Work**: Always verify that changes work. Run tests, run the server, or use appropriate validation commands before concluding a task.

## 2. Code Quality & Style
- **Follow Existing Patterns**: Match the existing coding style, naming conventions, and architecture of the project. Do not introduce new libraries or frameworks without permission.
- **Preserve Documentation**: Do not delete existing comments or docstrings unless they are invalidated by your code changes.
- **Atomic Changes**: Keep changes focused on the user's specific request. Do not sneak in unrelated refactors.

## 3. Communication
- When a task is complete, summarize what was changed and how it was tested.
- Do not apologize excessively or use filler phrases.
