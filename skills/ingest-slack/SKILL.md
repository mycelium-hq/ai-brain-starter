---
name: ingest-slack
description: Pulls recent messages from a Slack channel into the vault as queryable markdown. Use when the user says /ingest-slack <channel-name> [--days N], or asks to ingest, capture, sync, or pull a Slack channel into the vault. Writes one file per channel per day to External Inputs/Slack/<channel>/<date>.md. Auto-creates Decision Log stubs when trigger keywords (exception, incident, pricing, escalation, outage, edge case, refund) appear. Idempotent: re-running on the same day overwrites cleanly. Do NOT use for sending Slack messages, reading individual threads, or non-Slack sources.
---

# ingest-slack — Slack-to-vault connector

Ingests recent Slack messages into the vault as markdown the graphify pipeline can read and the rest of the AI Brain Starter substrate (decision log, session-close cascade, hooks) can act on.

This is the first connector in a pattern. Adding the next external source (Notion, Jira, email) means writing a new normalizer, not a new architecture.

## When to use

- User says `/ingest-slack <channel-name>` (with or without `--days N`)
- User asks to capture, sync, ingest, or pull a Slack channel into the vault
- User mentions wanting Slack threads available to the knowledge graph or session close

Do NOT use for:
- Sending Slack messages (use the Slack MCP `slack_send_message` directly)
- One-off thread reads (use `slack_read_thread`)
- Non-Slack sources (Notion, Jira, email get their own connectors)

## How it works

1. Resolve the channel name to a channel ID via `slack_search_channels`
2. Fetch messages from the last N days (default 7) via `slack_read_channel`
3. For each parent message with replies, pull the full thread via `slack_read_thread`
4. Normalize messages to vault markdown (chronological, one `##` per parent message, threads as `###` sub-sections)
5. Write to `External Inputs/Slack/<channel-name>/<YYYY-MM-DD>.md`
6. Scan the new file for trigger keywords (exception, incident, pricing, escalation, outage, edge case, one-off, refund, refund request, custom deal, special pricing)
7. For each match, create a Decision Log stub at `⚙️ Meta/Decisions/<YYYY-MM-DD>-slack-<channel>-<sha8(message_ts)>.md`
8. Print summary: file path, message count, edge cases detected

## Voice rules

- No em dashes (use commas, colons, periods, parentheses)
- No exclamation marks
- Direct, no fluff
- Spanish messages stay in Spanish; English stays in English
- Author names quoted verbatim from Slack (display name, not real name)

## Invocation

The skill is a thin orchestrator. The actual ingestion runs in Python at `~/.claude/skills/ingest-slack/ingest.py`. The skill assembles the Slack MCP tool calls, hands the raw payloads to `ingest.py`, and the script does the normalization, file write, and edge-case scan.

When invoked:

1. Parse arguments: channel name (required), `--days N` (optional, default 7)
2. Call `slack_search_channels` with the channel name. If zero results, report "channel not found" and stop. If multiple, ask the user to disambiguate.
3. Call `slack_read_channel` with the resolved channel ID and a `limit` of 100. Compute `oldest` as the Unix timestamp for `now - N days`.
4. For each message in the response that has `reply_count > 0`, call `slack_read_thread` with the parent `ts`.
5. Hand the assembled payload (channel metadata + parent messages + threads) to `ingest.py` as JSON on stdin.
6. `ingest.py` writes the vault file, the decision stubs, and prints a summary.
7. Surface the summary to the user. If decision stubs were created, list the file paths so the user can review and fill in the outcomes.

## Output contract

The vault file at `External Inputs/Slack/<channel>/<YYYY-MM-DD>.md` has frontmatter:

```yaml
---
type: external-input
source: slack
channel: <channel-name>
channel_id: <Cxxxx>
date_range: <YYYY-MM-DD>..<YYYY-MM-DD>
message_count: <int>
ingested_at: <ISO 8601 timestamp>
---
```

Body is chronological. Each parent message is a `## YYYY-MM-DD HH:MM <author>` section with the message body as its content. Thread replies become `### YYYY-MM-DD HH:MM <author>` sub-sections.

Decision Log stubs created at `⚙️ Meta/Decisions/<date>-slack-<channel>-<sha8>.md` carry frontmatter that matches the existing decision schema so the aggregator picks them up cleanly.

## Idempotency

Re-running `/ingest-slack <channel> --days N` on the same calendar day overwrites the same vault file. The decision stub filenames hash the Slack message timestamp, so the same source message produces the same stub filename across re-runs. Re-runs do not duplicate; they refresh.

## Acceptance test

A successful run produces:
1. One new (or refreshed) file at `External Inputs/Slack/<channel>/<date>.md`
2. Zero or more new decision stubs at `⚙️ Meta/Decisions/<date>-slack-<channel>-<sha8>.md`
3. A stdout summary: `Wrote N messages to <path>. Detected K edge cases. Stubs at: <paths>.`

If the channel resolves but contains no messages in the date range, write the file anyway with `message_count: 0` so re-runs are still idempotent and the absence is recorded.
