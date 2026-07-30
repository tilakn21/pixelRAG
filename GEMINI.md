# Gemini / Antigravity Specific Rules

This file contains overrides and specific instructions for the Gemini agent (Antigravity). These rules build upon the shared instructions in `AGENTS.md`.

## 1. Tool Usage
- Prioritize using specific, native tools (like `view_file`, `list_dir`, `replace_file_content`) over generic bash commands.
- Avoid using `cat`, `grep`, or `sed` in bash commands; rely on the provided built-in alternatives.

## 2. Planning and Artifacts
- **Planning Mode**: If a task involves significant architectural changes, stop and generate an `implementation_plan.md` artifact. Wait for user approval before modifying code.
- **Task Tracking**: For complex tasks, create and maintain a `task.md` artifact to track progress.
- **Walkthroughs**: Upon completing a complex task, summarize the changes in a `walkthrough.md` artifact, incorporating visual evidence (like screenshots or recordings) if applicable.

## 3. Persistent Knowledge
- **Check KIs First**: Always check the Knowledge Items (KIs) at the start of a conversation to avoid redundant work and adhere to established project patterns.
- If an established pattern exists for adding a feature or writing a test, follow it strictly.
