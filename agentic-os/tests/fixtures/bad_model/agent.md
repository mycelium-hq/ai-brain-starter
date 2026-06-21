---
name: typo-model
description: NEGATIVE CONTROL — an agent whose model: is not a valid Claude Code alias. validate_agents.py MUST reject it; Claude Code does not document a safe fallback for an invalid model value, so a typo would silently mis-pin. Never installed.
role: reviewer
tools: [Read, Grep, Glob]
model: gpt4o
---

# Bad model (fixture)

`model: gpt4o` is not a valid Claude Code model alias (`opus` / `sonnet` / `haiku`
/ `inherit`, or a full `claude-*` id). The validator must FAIL on it so a typo
never ships a silently mis-pinned agent.
