---
name: ingest-notion
description: Pulls recent pages or database entries from Notion into the vault as queryable markdown. Use when the user says /ingest-notion <database-or-page> [--depth N], or asks to ingest, capture, sync, or pull a Notion database or page tree into the vault. Writes one file per database (or root page) per day to External Inputs/Notion/<database-name>/<date>.md. Idempotent: re-running on the same day overwrites cleanly. Do NOT use for creating Notion pages, editing blocks, or non-Notion sources.
argument-hint: "<database-id-or-page-id> [--depth N]"
---

# ingest-notion: Notion-to-vault connector

Ingests recent Notion database entries or a page subtree into the vault as markdown the graphify pipeline can read and the rest of the AI Brain Starter substrate (decision log, session-close cascade, hooks) can act on.

This is the third connector in the ingest-* pattern. Adding the next external source means writing a new normalizer, not a new architecture.

## When to use

- User says `/ingest-notion <database-id-or-page-id>` (with or without `--depth N`)
- User asks to capture, sync, ingest, or pull a Notion database or page subtree into the vault
- User mentions wanting Notion pages available to the knowledge graph or session close

Do NOT use for:
- Creating or editing Notion pages (use the Notion MCP write tools directly)
- One-off page reads (use the Notion MCP read tools directly)
- Non-Notion sources (Slack, GitHub, email get their own connectors)

## How it works

1. Parse the `<database-id-or-page-id>` argument. Notion IDs are 32 hex chars, with or without dashes.
2. Probe whether the ID is a database or a page via the Notion MCP. Databases get listed with `query_database`; pages get walked with `get_page` plus `get_block_children` recursively to `--depth`.
3. For databases: pull all entries (paged), capture title, last_edited_time, and a body excerpt assembled from the top-level rich-text properties.
4. For pages: walk the block tree to the requested depth (default 1, meaning the page plus its direct child blocks; depth 2 includes one level of nested children, and so on, capped at 5).
5. Normalize each item to a markdown block with title, URL, last edited, author (if available), property summary or body excerpt.
6. Write to `External Inputs/Notion/<database-or-page-slug>/<YYYY-MM-DD>.md`.
7. Print summary: file path, page count, depth used.

## Voice rules

- No em dashes (use commas, colons, periods, parentheses)
- No exclamation marks
- Direct, no fluff
- Page titles quoted verbatim from Notion
- Body excerpts truncated at 800 characters per page to keep the vault file readable

## MCP requirement

This skill calls a Notion MCP for read access (`query_database`, `get_page`, `get_block_children`). If no Notion MCP is connected to your Claude Code install, the skill prints a clear error naming the missing MCP and instructions for connecting one (the canonical reference is the official `@modelcontextprotocol/server-notion` package or the Notion MCP shipped by makenotion). The skill does not silently fall back to the public Notion API; it surfaces the gap so you can wire the MCP once and run the skill cleanly.

If the MCP is connected but the integration token lacks access to the requested database or page, the call returns 404 or 403 and the skill reports the access issue.

## Invocation

The skill is a thin orchestrator. The actual normalization runs in Python at `~/.claude/skills/ingest-notion/ingest.py` (or the public-repo path). The skill assembles the Notion MCP tool calls, hands the raw payloads to `ingest.py` as JSON on stdin, and the script writes the file.

When invoked:

1. Parse arguments: `<id>` (required), `--depth N` (optional, default 1).
2. Verify a Notion MCP is available. If not, print the missing-MCP error and stop.
3. Probe the ID. If `query_database` succeeds, treat as database. Else fall back to `get_page`.
4. For databases: page through `query_database` collecting all entries.
5. For pages: call `get_page` for the root, then recursively `get_block_children` to `--depth`, capping at 5.
6. Hand the assembled payload (root metadata + items) to `ingest.py` as JSON on stdin.
7. `ingest.py` writes the vault file and prints a summary.
8. Surface the summary to the user.

## Output contract

The vault file at `External Inputs/Notion/<slug>/<YYYY-MM-DD>.md` has frontmatter:

```yaml
---
type: external-input
source: notion
database_id: <uuid-with-dashes>     # set when root is a database
page_id: <uuid-with-dashes>         # set when root is a single page
root_kind: database                 # or "page"
page_count: <int>
ingested_at: <ISO 8601 timestamp>
entity_ids:
  notion: [<uuid>, ...]             # every Notion page id captured
---
```

Body is grouped by item, each item with title, URL, last_edited, and a body excerpt. For database mode the items are sorted by `last_edited_time` descending. For page mode the body is rendered as a nested block tree to the requested depth.

The `entity_ids.notion` array conforms to the cross-type frontmatter contract so downstream consumers (graph builders, fact aggregators, agents) can join Notion pages to their source records without re-parsing the body.

## Idempotency

Re-running `/ingest-notion <id> --depth N` on the same calendar day overwrites the same vault file. The file path is keyed by date and root slug, so the same source produces the same path across re-runs. Re-runs do not duplicate; they refresh.

## Acceptance test

A successful run produces:
1. One new (or refreshed) file at `External Inputs/Notion/<slug>/<date>.md`
2. A stdout summary: `Wrote N page(s) to <path>.`

If the database resolves but contains no entries, write the file anyway with `page_count: 0` so re-runs are still idempotent and the absence is recorded.
