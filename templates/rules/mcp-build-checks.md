---
type: rule
purpose: Pre-flight checklist for ANY work on an MCP server — new build, extension, debug, deploy.
trigger: Read when a prompt mentions MCP, FastMCP, mcp server, connector, agent build, OR when Write/Edit targets any path containing -mcp/ or mcp-server/.
---

# MCP Build Checks

> **Binding contract.** Every single MCP-related task — new build, add-a-tool extension, scope change, bug fix, re-registration — runs the relevant checklist below BEFORE any Write, Edit, or Bash that mutates state. "I'm just adding a tool" is NOT an exception. The runbook at `docs/MCP_BUILD_RUNBOOK.md` is the full source of truth; this file is the short trigger card.

## Step 0 — ALWAYS

1. Read `docs/MCP_BUILD_RUNBOOK.md` in full. This session, not last session. Full file, not skim.
2. Pick the correct checklist below based on task shape.

## Mode A — New MCP from scratch

Run the full **PRE-FLIGHT CHECKLIST** in the runbook. All of it. No shortcuts. Especially:
- Existing-MCP audit (search the MCP registry and GitHub for servers that already wrap this service)
- Official API-surface scan — independent of what existing MCPs expose
- Optimization Pass (mandatory, not optional)
- Verify FastMCP install + Python deps
- Registration goes in vault `.mcp.json`, NOT `~/.claude/.mcp.json` (ghost path)

## Mode B — Extending an existing MCP (adding tools, scopes, or services)

Shorter, but still binding. Most skips happen here because extension feels "lighter" than new build. It is not.

1. **Read existing server files first.** `server.py`, all `*_tools.py`, `accounts.py`, `requirements.txt`, `SETUP.md`, `README.md`. Understand v1 before changing v1.
2. **Glob the target directory before the first Write.** A prior session or sub-agent may have already stubbed the new tool files. Read before Write. Otherwise Write fails with "File has not been read yet" and you lose the stub's content.
3. **Existing-MCP audit still required.** Other MCPs for the new service may have solved gotchas you'll otherwise rediscover.
4. **Official API-surface scan still required.** Do NOT skip just because you think you know the service. Every extension is a chance to ship endpoints existing MCPs ignore.
5. **Optimization Pass on the addition.** Does the new surface duplicate a paid tool? Can N tools collapse to 1 with an opt-in param? Does the new service need a new backend or can it reuse the existing factory?
6. **OAuth scope additions force re-consent.** See Scope-Change Protocol below.
7. **Register via edit, not duplicate.** If the MCP is already in vault `.mcp.json`, leave the entry; just restart Claude Code to pick up new tools.
8. **After edit: `python3 -c "import server"` in the MCP dir before declaring done.**

## Scope-Change Protocol (OAuth-connected MCPs)

Google, Microsoft, Slack, Notion — every OAuth provider refuses to silently widen a refresh token's scope. Adding a scope requires:

1. Update the `SCOPES` list in `accounts.py` (or equivalent).
2. Document in SETUP.md: revoke access at the provider's account-permissions page for each already-authorized account.
3. User runs the `*_account_add` flow again per account. New consent screen shows the expanded scope list.
4. Only after step 3 does the refresh token cover the new endpoints.

Never assume that bumping the scope list in code silently upgrades existing tokens. It does not. Every account re-OAuths or every new-scope tool call 403s.

## Parallel-Session Guard

Claude Code allows multiple sessions to touch the same directory. If you are in a worktree and another session (or agent) is operating on the same MCP:

- Always `Glob` + `Read` before `Write` — detect stubs from the parallel session.
- If a file exists that you intended to create, read it, validate quality, `Edit` the gaps rather than overwriting.
- Accept that the file may reflect a different design philosophy than yours. Either harmonize via Edit or explicitly replace with justification.

## Session-close duty

If this session touched any MCP file, the session-close rule must:
- Confirm `python3 -c "import server"` passes.
- Confirm `.mcp.json` parses: `python3 -c "import json; json.load(open('<path>'))"`.
- Add a build-log entry to your MCP Build Log (vault-local, wherever you keep build history).
- Note any new lessons to append to the runbook.

## When this rule is most likely violated

- "Just adding one tool" — Mode B, still binding.
- "Fixing a typo in server.py" — Still read the file before Edit, still verify import after.
- "Parallel session already did most of the work" — especially dangerous; apply Parallel-Session Guard.
- "Extension, so pre-flight doesn't apply" — NO. Mode B exists for this exact case.
