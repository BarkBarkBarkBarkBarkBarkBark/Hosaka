---
name: hosaka-task-manager
description: Maintain Hosaka's runtime task system. Use when the operator asks for prioritization, a top-3 list, daily planning, task creation, task updates, blocked-task review, or project status derived from the canonical task file.
---

# Hosaka Task Manager

Use the runtime manager files as the system of record:

- Charter: `~/.picoclaw/workspace/manager/charter.yaml`
- Tasks: `~/.picoclaw/workspace/memory/TASKS.md`

## Workflow

1. Read the charter first.
2. Read the current task file.
3. Score and prioritize tasks using the charter.
4. When adding or updating tasks, persist the change in `TASKS.md` in the same turn.
5. For "top 3" or "what now", answer from the task file instead of improvising.

## Rules

- Prefer concrete next actions.
- Keep task titles short and actionable.
- Mark blocked tasks explicitly.
- If the task file is missing, create it from the runtime template and continue.
