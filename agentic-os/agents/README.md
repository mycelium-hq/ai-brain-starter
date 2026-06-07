# Agents

Each agent is one specialist, one domain, under 100 lines. The frontmatter is a
**declarative contract** the harness enforces:

| Field | Meaning |
|---|---|
| `name` | how the kernel routes to it |
| `description` | when to use it (the router reads this) |
| `role` | `planner` / `reviewer` / `research` are **read-only** roles; `resolver` writes |
| `tools` | the EXACT tool surface. Claude Code restricts the agent to this list — a tool not listed cannot be called |
| `model` | pinned per agent: heavier model for planning, lighter for execution |

## The safety boundary is the `tools:` list

A read-only agent (`planner` / `reviewer`) lists only `Read, Grep, Glob`. It
**cannot** `Write`, `Edit`, or run `Bash` — not by policy, by construction. The
harness will not hand it a tool it did not declare.

That invariant is checkable. `validate_agents.py` (shipped to `.claude/hooks/`)
parses every spec and FAILS if a read-only role declares a mutating tool, or if an
agent is missing its `model` pin. Run it in CI:

```sh
python3 .claude/hooks/validate_agents.py .claude/agents
```

A `role: planner` that lists `Write` is a contradiction — the validator rejects it
so the lie never ships.

## Adding an agent

Drop a `<name>.md` with the five frontmatter fields, keep it under 100 lines, give
it one job. Read-only by default; grant write tools only to a `resolver`-class
agent that needs them.
