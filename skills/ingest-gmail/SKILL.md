---
name: ingest-gmail
description: Pulls recent Gmail messages matching a label or query into the vault as queryable markdown. Use when the user says /ingest-gmail <label-or-query> [--days N], or asks to ingest, capture, sync, or pull a Gmail label or query into the vault. Writes one file per scope per day to External Inputs/Gmail/<label>/<date>.md. Truncates each message body to 500 chars to limit bulk PII. Idempotent: re-running on the same day overwrites cleanly. Do NOT use for sending email, replying, or non-Gmail sources.
---

# ingest-gmail, Gmail-to-vault connector

Ingests recent Gmail messages (matching a label or a free-text Gmail query) into the vault as markdown the graphify pipeline can read and the rest of the AI Brain Starter substrate (decision log, session-close cascade, hooks) can act on.

This is one of a small family of ingestion connectors (slack, linear, gmail). Adding the next external source means writing a new normalizer, not a new architecture.

## When to use

- User says `/ingest-gmail <label-or-query>` (with or without `--days N`)
- User asks to capture, sync, ingest, or pull a Gmail label or saved query into the vault
- User mentions wanting recent email threads available to the knowledge graph or session close

Do NOT use for:
- Sending email (use the Google Workspace MCP `gmail_send`)
- Replying to a message (use `gmail_reply`)
- Reading a single message (use `gmail_read`)
- Non-Gmail sources (Slack, Linear, Notion get their own connectors)

## PII awareness, read this before running

Gmail content is the highest-PII surface in the vault. A typical inbox carries personal email addresses, phone numbers, full names, contract numbers, billing details, internal company memos, and confidential business discussion. Every ingestion writes a copy of that data into the vault.

Operator obligations:

1. **Treat the output file as confidential.** Never commit it to a public repository. Never paste it into a public chat. Never share it outside the vault owner.
2. **Never select labels you do not control.** Avoid ingesting a shared inbox or a delegated mailbox unless you have the inbox owner's explicit consent.
3. **Scrub before sharing.** If the file ever needs to leave the vault (e.g., as part of a support thread, a bug report, an example for documentation), scrub names, addresses, phone numbers, account numbers, and message bodies first. The `humanizer` and `extract-rules-from-vault` skills have scrub helpers; use them.
4. **Body truncation is a defense, not a guarantee.** This skill truncates each message body to 500 characters to limit the volume of PII captured per run. Truncation does not remove personal data; it caps how much. The first 500 chars of an email almost always contain the sender, the recipient, and a fragment of the topic.
5. **Restrict the public ai-brain-starter footprint.** The skill code lives in the public repo. The vault output never goes there. The personal-data scrub gate on the public repo will reject any file that contains personal names or company tokens.

If any of these obligations is unclear, do not run the skill. Ask first.

## How it works

1. Resolve the input as either a label name (matched via `gmail_labels_list`) or a free-text Gmail query (anything containing search operators like `from:`, `to:`, `subject:`, `is:`, `after:`, `before:`).
2. Fetch messages from the last N days (default 7) via `gmail_search`. Apply the day window via `after:YYYY/MM/DD` in the query string.
3. For each match, call `gmail_read` (without `keep_html`) to get the plain-text body.
4. Normalize messages to vault markdown (chronological, one `##` per message, body truncated to 500 chars).
5. Write to `External Inputs/Gmail/<scope>/<YYYY-MM-DD>.md` where `<scope>` is the label name (slugified) or `query-<sha8>` if the input was a free-text query.
6. Print summary: file path, message count.

## Voice rules

- No em dashes (use commas, colons, periods, parentheses)
- No exclamation marks
- Direct, no fluff
- Sender and subject quoted verbatim from Gmail
- Body excerpts are the first 500 chars verbatim, then truncated with `[...truncated]`

## Invocation

The skill is a thin orchestrator. The actual ingestion runs in Python at `${SKILL_ROOT}/ingest.py`. The skill assembles the Google Workspace MCP tool calls, hands the raw payloads to `ingest.py`, and the script does the normalization, file write, and frontmatter.

When invoked:

1. Parse arguments: scope (required, either a label name or a Gmail search query), `--days N` (optional, default 7).
2. If the scope contains a Gmail search operator (`from:`, `to:`, `subject:`, `is:`, `has:`, `label:`, `after:`, `before:`, `in:`), treat it as a free-text query. Otherwise treat it as a label name.
3. For a label name: call `gmail_labels_list` and verify the label exists. If not, report "label not found" and stop.
4. Build the Gmail query: for a label, use `label:<label-name> after:YYYY/MM/DD`. For a free-text query, append ` after:YYYY/MM/DD` to the user's query.
5. Call `gmail_search` with the query and `limit: 50` (the per-page max). Do not paginate beyond this; the skill is for a daily snapshot, not a full archive scan.
6. For each result, call `gmail_read` with that message ID.
7. Hand the assembled payload (scope metadata + messages) to `ingest.py` as JSON on stdin.
8. `ingest.py` writes the vault file, truncates each body to 500 chars, and prints a summary.
9. Surface the summary to the user.

## Output contract

The vault file at `External Inputs/Gmail/<scope>/<YYYY-MM-DD>.md` has frontmatter:

```yaml
---
type: external-input
source: gmail
label_or_query: <verbatim string>
scope_kind: label | query
date_range: <YYYY-MM-DD>..<YYYY-MM-DD>
message_count: <int>
ingested_at: <ISO 8601 timestamp>
entity_ids:
  gmail:
    - <gmail-message-id-1>
    - <gmail-message-id-2>
---
```

Body is chronological. Each message is a `## YYYY-MM-DD HH:MM <sender>` section with the subject as the first line of the body, then the truncated body excerpt. Long bodies end with `[...truncated]`.

## Idempotency

Re-running `/ingest-gmail <scope> --days N` on the same calendar day overwrites the same vault file. No append. The `entity_ids.gmail` array reflects exactly the messages in the current window.

## Acceptance test

A successful run produces:
1. One new (or refreshed) file at `External Inputs/Gmail/<scope>/<date>.md`
2. A stdout summary: `Wrote N message(s) to <path>.`

If the scope resolves but contains no matching messages in the window, write the file anyway with `message_count: 0` so re-runs are still idempotent and the absence is recorded.

## Failure modes

- Google Workspace MCP not connected: `ingest.py` does not require the MCP. The MCP calls happen at the orchestration layer. If the LLM cannot reach the MCP, surface that error to the user, do not write a stub file.
- Label ambiguity: ask the user before running the ingestion.
- Free-text query returns zero results: write the empty-window file and report `message_count: 0`.
- Body parsing failure: emit `_(body unavailable)_` for that message; keep the rest of the file intact.
