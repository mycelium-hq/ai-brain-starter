---
type: config
skill: daily-journal
created: 2026-05-08
last_updated: 2026-05-08
# Data sources for /journal Step 0.
# Default: privacy-preserving. Each "off" source is skipped silently.
# Each "on" source is pulled when the matching MCP is connected.
data_sources:
  rescuetime: on              # productivity pulse, hours, top apps (RescueTime MCP)
  session_captures: on        # ⚙️ Meta/Session Captures.md — quotes from your own Claude sessions
  todays_activity: on         # today's git commits, modified files, session files in your own vault
  calendar: off               # today's calendar events (Google Workspace MCP) — opt-in
  imessage_24h: off           # iMessage threads with traffic in last 24h — opt-in (sees private conversations)
  whatsapp_24h: off           # WhatsApp threads with traffic in last 24h — opt-in (sees private conversations)
# Per-source filters (only consulted when the source is "on")
imessage_filters:
  exclude_chats: []           # phone numbers, emails, or contact names to skip on every pull
  only_unread: false          # if true, restrict to chats with unread messages
whatsapp_filters:
  exclude_chats: []
  only_unread: false
calendar_filters:
  include_calendars: []       # leave empty to pull all calendars; or list calendar IDs to whitelist
---

# Daily Journal Config

This file controls what data sources `/journal` pulls during Step 0 of every journaling session. The skill reads it before any data fetch.

## Privacy stance — opt-in for cross-platform

Three sources are ON by default because they're your own vault data:
- **RescueTime** — productivity numbers from your own account.
- **Session Captures** — quotes you typed yourself in your own Claude sessions.
- **Today's activity** — git commits, modified files, and session notes inside your own vault.

Three sources are OFF by default because they cross into private conversations:
- **iMessage** — pulls the threads you had on your phone.
- **WhatsApp** — pulls the threads you had in the app.
- **Calendar** — pulls the meetings and events on your day.

When you turn one ON, the skill will only pull during a `/journal` session, never on its own. The threads it sees are the same threads you'd see by opening your phone. Nothing leaves your machine. The journal narrative stays in your own voice; relational events get folded in as context, not as quotes (except where you ask for verbatim).

## Why opt-in

Pulling iMessage / WhatsApp / Calendar gives the journal much richer context — relational events, repair conversations, voice notes, who you spent time with. It also means the model sees private conversations. That's a trade-off you should make explicitly, not by default.

## Turn on a source

Change `off` to `on` in the YAML frontmatter above. Save. Next `/journal` will pick it up. The skill never re-prompts; you stay in control.

## Filter a noisy chat

Add the phone number, email, or contact name to `exclude_chats` under the matching source. The skill skips that thread on every pull.

## Common configs

**"All in" — full context every session:**

```yaml
data_sources:
  rescuetime: on
  session_captures: on
  todays_activity: on
  calendar: on
  imessage_24h: on
  whatsapp_24h: on
```

**"Vault only" — never see messages or calendar:**

```yaml
data_sources:
  rescuetime: on
  session_captures: on
  todays_activity: on
  calendar: off
  imessage_24h: off
  whatsapp_24h: off
```

**"Heavy day, exclude work threads":**

```yaml
data_sources:
  rescuetime: on
  session_captures: on
  todays_activity: on
  calendar: on
  imessage_24h: on
  whatsapp_24h: on
imessage_filters:
  exclude_chats: ["work-group-chat-name"]
whatsapp_filters:
  exclude_chats: ["+15551234567"]
```

## How the skill installs this file

If `Meta/journal-config.md` (or `⚙️ Meta/journal-config.md` for emoji-prefixed vaults) does not exist when `/journal` runs, the skill copies this template into your vault and asks once whether to opt in to any cross-platform sources. Your answer is recorded in the file. The skill never re-prompts after that — you stay in control of what gets pulled by editing the file directly.
