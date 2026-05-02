---
name: ingest-whatsapp
description: Pulls recent messages from a WhatsApp chat (group or direct) into the vault as queryable markdown. Use when the user says /ingest-whatsapp <chat-name-or-jid> [--days N], or asks to ingest, capture, sync, or pull a WhatsApp chat into the vault. Writes one file per chat per day to External Inputs/WhatsApp/<chat-slug>/<date>.md. Auto-creates Decision Log stubs when trigger keywords (exception, incident, pricing, escalation, outage, edge case, refund) appear. Idempotent: re-running on the same day overwrites cleanly. Receive-only, never sends. Do NOT use for sending WhatsApp messages or non-WhatsApp sources.
---

# ingest-whatsapp, WhatsApp-to-vault connector

Ingests recent WhatsApp messages (from a group chat or a one-on-one conversation) into the vault as markdown the graphify pipeline can read and the rest of the AI Brain Starter substrate (decision log, session-close cascade, hooks) can act on.

This is one of a small family of ingestion connectors (slack, gmail, linear, github, notion, whatsapp). Adding the next external source means writing a new normalizer, not a new architecture.

WhatsApp is often the operator's primary team channel, so this connector ships with the same trigger-keyword scan and decision-stub pattern as ingest-slack.

## When to use

- User says `/ingest-whatsapp <chat-name-or-jid>` (with or without `--days N`)
- User asks to capture, sync, ingest, or pull a WhatsApp chat into the vault
- User mentions wanting recent WhatsApp threads available to the knowledge graph or session close

Do NOT use for:
- Sending WhatsApp messages (use the WhatsApp MCP `send_message` plus `confirm_send`)
- Reactions or replies (use the WhatsApp MCP `send_reaction`, `send_reply_quote`)
- One-off message reads (use `list_messages` directly)
- Non-WhatsApp sources (Slack, Gmail, Linear, Notion, GitHub get their own connectors)

## PII awareness, read this before running

WhatsApp content is one of the highest-PII surfaces in the vault, on par with Gmail and arguably more sensitive in tone. A WhatsApp chat carries real phone numbers as JIDs, given names from the operator's CRM, family conversation, friend group banter, contractor coordination, voice-note transcriptions, and the kind of blunt informal writing people produce when they assume a tight audience. Every ingestion writes a copy of that data into the vault.

Operator obligations:

1. **The output stays local.** This connector writes to the operator's local Obsidian vault only. The vault repo is local-only by convention (no remote configured), so the ingested file does not leave the machine unless the operator copies it elsewhere. Treat the output file as confidential. Never commit it to a public repository. Never paste it into a public chat. Never share it outside the vault owner.
2. **Group chats capture non-consenting senders.** When you ingest a group chat, every message from every other participant lands in the vault. Those participants did not consent to that ingest, did not opt in, and do not know it happened. This is fine for personal sense-making and pattern-spotting. It is not fine as a basis for any multi-tenant tooling, dataset publication, or shared analysis. If you find yourself wanting to surface a group-chat ingest beyond the vault owner, stop and reconsider.
3. **Personal use only.** This skill is for one operator processing their own conversational record. Do not point it at chats the operator is not a participant in. Do not run it on a delegated or shared device without the device owner's consent.
4. **Sender names are CRM-resolved.** The WhatsApp MCP returns sender names from the operator's local CRM lookup when available, falling back to the raw phone number when not. The vault file therefore mixes named participants and bare phone numbers. Both are PII. Treat the phone numbers as carefully as the names.
5. **Scrub before sharing.** If the file ever needs to leave the vault (e.g., as part of a support thread, a bug report, an example for documentation), scrub names, phone numbers, message bodies, and group titles first. The `humanizer` and `extract-rules-from-vault` skills have scrub helpers; use them.
6. **Public ai-brain-starter footprint stays clean.** The skill code lives in the public repo. The vault output never goes there. The personal-data scrub gate on the public repo will reject any push that contains personal names or company tokens.

If any of these obligations is unclear, do not run the skill. Ask first.

## How it works

1. Resolve the chat-name argument to a chat JID. If the argument already looks like a JID (contains `@s.whatsapp.net` or `@g.us`), skip resolution. Otherwise, call `search_contacts` (for direct chats) or `list_chats` (for group chats) and match by name.
2. If the name matches multiple chats, ask the user to pick one. Do not guess.
3. Compute `oldest = now - N days` (default N=7) as a Unix-seconds cutoff.
4. Fetch recent messages via `list_messages(chat_jid, limit=200, include_crm_context=true)`. The MCP returns messages newest-first; filter to `timestamp >= oldest` in the orchestrator.
5. Normalize messages to vault markdown (chronological, one `##` per message, reactions and media references included as bullet metadata).
6. Write to `External Inputs/WhatsApp/<chat-slug>/<YYYY-MM-DD>.md`.
7. Scan the new file for trigger keywords (exception, incident, pricing, escalation, outage, edge case, one-off, refund, refund request, custom deal, special pricing).
8. For each match, create a Decision Log stub at `⚙️ Meta/Decisions/<YYYY-MM-DD>-whatsapp-<chat-slug>-<sha8(message_id)>.md`.
9. Print summary: file path, message count, edge cases detected.

## Voice rules

- No em dashes (use commas, colons, periods, parentheses)
- No exclamation marks
- Direct, no fluff
- Spanish messages stay in Spanish; English stays in English
- Author names quoted verbatim from WhatsApp (CRM-resolved name when present, raw phone-number JID when not)

## Invocation

The skill is a thin orchestrator. The actual ingestion runs in Python at `${SKILL_ROOT}/ingest.py`. The skill assembles the WhatsApp MCP tool calls, hands the raw payloads to `ingest.py`, and the script does the normalization, file write, and edge-case scan.

When invoked:

1. Parse arguments: chat (required, name or JID), `--days N` (optional, default 7).
2. Resolve the chat:
   - If the argument contains `@s.whatsapp.net` or `@g.us`, treat it as a JID and skip resolution.
   - Otherwise, call `search_contacts` with the argument and inspect results. If exactly one contact matches, use that JID. If multiple match, list candidates and ask. If none match, fall back to `list_chats(limit=50)` and look for a chat name that matches the argument; if still ambiguous, ask the user.
3. Call `list_messages(chat_jid, limit=200, include_crm_context=true)`. The MCP returns the most recent messages first.
4. In the orchestrator, filter to `timestamp >= now - N days`. If the count exceeds 200, surface a note that the lookback window may have been clipped and suggest the user run with a smaller `--days`.
5. Hand the assembled payload (chat metadata + filtered messages) to `ingest.py` as JSON on stdin.
6. `ingest.py` writes the vault file, the decision stubs, and prints a summary.
7. Surface the summary to the user. If decision stubs were created, list the file paths so the user can review and fill in the outcomes.

## Output contract

The vault file at `External Inputs/WhatsApp/<chat-slug>/<YYYY-MM-DD>.md` has frontmatter:

```yaml
---
type: external-input
source: whatsapp
chat_name: <verbatim chat name>
chat_jid: <jid>
chat_type: group | direct | broadcast
date_range: <YYYY-MM-DD>..<YYYY-MM-DD>
message_count: <int>
ingested_at: <ISO 8601 timestamp>
entity_ids:
  whatsapp:
    - <jid>
---
```

Body is chronological. Each message is a `## YYYY-MM-DD HH:MM <author>` section with:
- a bullet line for any media references (`- **Media:** image, audio, document, etc.`)
- a bullet line for any reactions (`- **Reactions:** emoji x N from <name>`)
- the message text as the section content
- empty messages render as `_(empty message)_`

Decision Log stubs created at `⚙️ Meta/Decisions/<date>-whatsapp-<chat-slug>-<sha8>.md` carry frontmatter that matches the existing decision schema so the aggregator picks them up cleanly.

## Idempotency

Re-running `/ingest-whatsapp <chat> --days N` on the same calendar day overwrites the same vault file. The decision stub filenames hash the WhatsApp message ID, so the same source message produces the same stub filename across re-runs. Re-runs do not duplicate; they refresh.

## Slug rules

- Lowercase the chat name, replace runs of non-alphanumeric characters with a single hyphen, strip leading and trailing hyphens.
- If the chat name is empty or the slug collapses to nothing (anonymous group, emoji-only title), fall back to `chat-<sha8(jid)>`.
- The slug is the only thing that lands on disk; it never leaves the vault.

## Acceptance test

A successful run produces:
1. One new (or refreshed) file at `External Inputs/WhatsApp/<chat-slug>/<date>.md`
2. Zero or more new decision stubs at `⚙️ Meta/Decisions/<date>-whatsapp-<chat-slug>-<sha8>.md`
3. A stdout summary: `Wrote N messages to <path>. Detected K edge cases. Stubs at: <paths>.`

If the chat resolves but contains no messages in the window, write the file anyway with `message_count: 0` so re-runs are still idempotent and the absence is recorded.

## Failure modes

- WhatsApp MCP not connected or bridge not authenticated: `ingest.py` does not require the MCP. The MCP calls happen at the orchestration layer. If the LLM cannot reach the MCP, surface that error to the user, do not write a stub file.
- Chat name ambiguous: ask the user before running the ingestion.
- Empty chat in the window: write the empty-window file and report `message_count: 0`.
- Anonymous chat (no display name available): use `chat-<sha8(jid)>` as the slug; the JID still ends up in frontmatter.
