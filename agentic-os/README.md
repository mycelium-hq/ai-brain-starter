# agentic-os — a clean agentic OS you can install into any repo

A minimal, declarative "operating system" for a coding agent: a small kernel that
orchestrates, specialist agents with **pinned models and tool surfaces**,
user-selectable **posture modes**, and **per-language quality rules that
auto-apply by file glob**. One command drops it into a fresh repo.

It is built on one idea: **the safety and quality boundaries should be declarative**
— readable in a markdown file, enforced by the harness, and checkable in CI — not
buried in prose the model may or may not follow.

## The four primitives

| Primitive | Where | What it gives you |
|---|---|---|
| **Kernel** | `kernel/CLAUDE.md` | A small COO/orchestrator. Routes work to agents in a plain markdown table. Stays under 100 lines — detail lives in the files it points to. |
| **Pinned agents** | `agents/*.md` | One specialist per file. `model:` pinned (heavy for planning, light for execution) and `tools:` pinned. A read-only `planner`/`reviewer` lists only `Read, Grep, Glob` and so **cannot** `Write` — a declarative safety boundary the harness enforces. |
| **Posture modes** | `contexts/*.md` | `dev` / `review` / `research` / `security`. Switch how you operate mid-session ("switch to review") without a full skill invocation. |
| **Paths-scoped rules** | `rules/<lang>/hooks.md` | Each rule declares a `paths:` glob (`**/*.ts`). When you edit a matching file, its checks auto-apply — zero per-file config. Add a language by dropping a folder. |

## Install

```sh
bash agentic-os/INSTALL.sh /path/to/your/repo
```

Lands `CLAUDE.md` (kernel) + `.claude/agents/` + `.claude/contexts/` +
`.claude/rules/<lang>/` + `.claude/hooks/` + a `data/` memory scaffold, plus a
`settings.agentic-os.json` snippet that wires the auto-apply hook. An existing
`CLAUDE.md` is never overwritten.

## The two enforcement mechanisms (not just templates)

Both load-bearing boundaries are **checkable**, each shipped with a negative
control that proves it fails on a violation:

- **`bin/validate_agents.py`** parses every agent spec and FAILS if a read-only
  role declares a mutating tool (`Write`/`Edit`/`Bash`/…) or omits its `model`
  pin. A `role: planner` that lists `Write` is rejected, so the lie never ships.

  ```sh
  python3 .claude/hooks/validate_agents.py .claude/agents
  ```

- **`bin/paths_scoped_rules.py`** is the auto-apply hook. Given an edited path it
  surfaces the matching language rules; on a non-matching path it stays silent
  (fail-open — it never blocks an edit). Wired as a `PostToolUse(Write|Edit)` hook.

Run the whole invariant + negative-control suite:

```sh
bash scripts/test-agentic-os.sh
```

## Why declarative

Prose rules degrade — the model follows them most of the time. A `tools:` list is
different: the harness will not hand an agent a tool it did not declare, so
"read-only" is a fact, not a hope. The kernel stays small so the agent's context
stays lean. The rules ride a glob so they cannot be forgotten on a new file. Every
boundary is one grep away from being audited.

## What Mycelium adds

This template is the free, public pattern. Mycelium's client install pack wraps it
with per-client agents and rules, a security layer, CI wiring, and onboarding — the
hardened, supported version for a team. The pattern here is yours to use either way.
