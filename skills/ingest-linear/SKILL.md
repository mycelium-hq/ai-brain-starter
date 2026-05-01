---
name: ingest-linear
description: Pulls recent Linear issues, comments, and status changes into the vault as queryable markdown. Use when the user says /ingest-linear <team-or-project> [--days N], or asks to ingest, capture, sync, or pull a Linear team or project into the vault. Writes one file per scope per day to External Inputs/Linear/<scope>/<date>.md. Idempotent: re-running on the same day overwrites cleanly. Do NOT use for creating Linear issues, updating status, or non-Linear sources.
---

# ingest-linear, Linear-to-vault connector

Ingests recent Linear activity (issues, comments, status changes) into the vault as markdown the graphify pipeline can read and the rest of the AI Brain Starter substrate (decision log, session-close cascade, hooks) can act on.

This is one of a small family of ingestion connectors (slack, linear, gmail). Adding the next external source means writing a new normalizer, not a new architecture.

## When to use

- User says `/ingest-linear <team-or-project>` (with or without `--days N`)
- User asks to capture, sync, ingest, or pull a Linear team or project into the vault
- User mentions wanting Linear issues available to the knowledge graph or session close

Do NOT use for:
- Creating Linear issues (use the Linear MCP `linear_createIssue`)
- Updating Linear status (use `linear_updateIssue`)
- Non-Linear sources (Slack, Gmail, Notion get their own connectors)

## How it works

1. Resolve the scope name to a team ID via `linear_getTeams`, or to a project ID via `linear_getProjects`. If both match, ask the user which one.
2. Fetch recent issues in scope. For a team scope, use `linear_searchIssues` with the team filter. For a project scope, use `linear_getProjectIssues`. Apply the day filter client-side, since the MCP search does not always support an updated-since cursor.
3. For each issue updated in the window, pull comments via `linear_getComments` and history (status/assignee changes) via `linear_getIssueHistory`.
4. Normalize to vault markdown (chronological, one `##` section per issue, comments and history events as `###` sub-sections under the issue).
5. Write to `External Inputs/Linear/<scope>/<YYYY-MM-DD>.md`.
6. Print summary: file path, issue count, comment count, history event count.

## Voice rules

- No em dashes (use commas, colons, periods, parentheses)
- No exclamation marks
- Direct, no fluff
- Issue titles, comment bodies, and author names quoted verbatim from Linear

## Invocation

The skill is a thin orchestrator. The actual ingestion runs in Python at `${SKILL_ROOT}/ingest.py`. The skill assembles the Linear MCP tool calls, hands the raw payloads to `ingest.py`, and the script does the normalization, file write, and frontmatter.

When invoked:

1. Parse arguments: scope name (required), `--days N` (optional, default 7).
2. Call `linear_getTeams`. If the scope matches a team key (e.g. `ENG`) or team name, capture the team ID. If no match, call `linear_getProjects` and try a project name match.
3. If neither matches, report "team or project not found" and stop. If both match, ask the user to disambiguate.
4. For a team scope, call `linear_searchIssues` with `teamId` filter and `limit: 100`. For a project scope, call `linear_getProjectIssues` with the project ID and `limit: 100`.
5. Compute the cutoff timestamp (`now - N days`). Filter issues whose `updatedAt` is older than the cutoff.
6. For each surviving issue, call `linear_getComments` (limit 50) and `linear_getIssueHistory` (limit 25).
7. Hand the assembled payload (scope metadata + issues + comments + history) to `ingest.py` as JSON on stdin.
8. `ingest.py` writes the vault file and prints a summary.
9. Surface the summary to the user.

## Output contract

The vault file at `External Inputs/Linear/<scope>/<YYYY-MM-DD>.md` has frontmatter:

```yaml
---
type: external-input
source: linear
scope: <team-key-or-project-name>
scope_kind: team | project
team_id: <uuid or null>
project_id: <uuid or null>
date_range: <YYYY-MM-DD>..<YYYY-MM-DD>
issue_count: <int>
comment_count: <int>
history_count: <int>
ingested_at: <ISO 8601 timestamp>
entity_ids:
  linear:
    - <ABC-123>
    - <ABC-124>
---
```

Body is chronological by issue `updatedAt`. Each issue is a `## <ABC-123> <title>` section with status, assignee, priority, and the issue description. Comments become `### Comment <YYYY-MM-DD HH:MM> <author>` sub-sections. History events become `### Status change <YYYY-MM-DD HH:MM>` sub-sections.

## Idempotency

Re-running `/ingest-linear <scope> --days N` on the same calendar day overwrites the same vault file. No append. The `entity_ids.linear` array reflects exactly the issues in the current window.

## Acceptance test

A successful run produces:
1. One new (or refreshed) file at `External Inputs/Linear/<scope>/<date>.md`
2. A stdout summary: `Wrote N issue(s), M comment(s), K history event(s) to <path>.`

If the scope resolves but contains no matching issues in the window, write the file anyway with `issue_count: 0` so re-runs are still idempotent and the absence is recorded.

## Failure modes

- Linear MCP not connected: `ingest.py` does not require the MCP. The MCP calls happen at the orchestration layer. If the LLM cannot reach the MCP, surface that error to the user, do not write a stub file.
- Scope ambiguity: ask the user before running the ingestion.
- Empty scope: write the empty-window file and report `issue_count: 0`.
