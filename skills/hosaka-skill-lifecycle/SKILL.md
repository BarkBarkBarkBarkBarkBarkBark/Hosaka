---
name: hosaka-skill-lifecycle
description: Govern Hosaka's use of skills. Use when deciding whether to use an installed skill, search for a skill, install one, or author a new skill for a recurring workflow.
---

# Hosaka Skill Lifecycle

Use the canonical skill catalog first:

- Catalog: `~/.picoclaw/workspace/skills/catalog/index.yaml`

## Workflow

1. Check the catalog for an obvious Hosaka-native skill.
2. If nothing fits, search installed or available skills.
3. Install a skill when it clearly improves execution and the workflow is not unique.
4. Author a new skill when the workflow repeats and no suitable skill exists.
5. Keep new skills concise and procedural.

## Rules

- Prefer existing skills before inventing a new workflow.
- Do not create a skill for one-off work unless the operator asks.
- If a workflow is likely to recur, capture it as a skill with a small, clear trigger description.
