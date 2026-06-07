---
name: planner
description: NEGATIVE CONTROL — a read-only planner role that wrongly declares mutating tools. validate_agents.py MUST reject this. It exists only to prove the guard fails on a violation; it is never installed.
role: planner
tools: [Read, Grep, Glob, Write, Edit]
model: opus
---

# Bad planner (fixture)

This file is a poisoned fixture. A `role: planner` is declared read-only, but its
`tools:` list includes `Write` and `Edit` — a contradiction that would hand the
"read-only" planner real mutation authority. `validate_agents.py` must FAIL on it.
If the validator ever passes this, the declarative tool-surface boundary is dead.
