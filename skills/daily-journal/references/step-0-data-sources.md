# Daily journal: Step 0 data sources (details)

Read this when SKILL.md Step 0 sends you here: after the preflight, for each per-source pull (0a through 0g), the opt-in rationale, and the seeds display.

**0a. RescueTime** (gated on `data_sources.rescuetime: on`). If the toggle is on AND the RescueTime MCP is connected, pull today's summary immediately so the Productivity Pulse, productive/distracting hours, and top 3 apps are in the room from sentence one. Otherwise skip silently.

**0b. Session Captures** (gated on `data_sources.session_captures: on`). Read `⚙️ Meta/Session Captures.md` (or your vault's equivalent staging file) in full. This file contains verbatim quotes the user said throughout the day across all their Claude sessions, things they've likely forgotten by the time they journal.

**0c. Today's activity** (gated on `data_sources.todays_activity: on`). Captures.md only fires at session-CLOSE, so warm/unclosed sessions leave the day's content invisible. Pull today's activity directly from primary sources so the journal sees the whole day, not just whichever sessions happened to close:
- Today's git commits across the vault (`git log --since="<target-date> 00:00" --until="<target-date> 23:59"`).
- Files modified in the vault today (filter relevant extensions, exclude `.git/`, `.next/`, `node_modules`, caches, `.bak-` backups).
- Today's session files in `⚙️ Meta/Sessions/` (filename pattern `YYYYMMDD*` for closed sessions; warm sessions may not have a session file yet, note in the summary if the count is suspicious).
- RescueTime hours summary (already pulled in 0a if enabled).

Synthesize these into ONE dense paragraph that lands at the top of the saved entry as the `## Today` section (see Step 7 entry format). Concrete: PR numbers, test count deltas, file counts, hour totals, named events, named people. Inventory shape, not narrative.

**0d-PRIMARY. Voice notes the user sent to their own self-chat (gated on `data_sources.self_chat_voice_notes: on`).** Some people dictate short voice notes to their own number during the day *specifically* as journal fuel. For them these are not background colour — they are the raw material of the entry, and they have to be pulled BEFORE the opener, not after. When the toggle is on, go through the live WhatsApp MCP directly rather than the on-demand reader in 0d: that reader digests text threads, and a self-chat's whole value is in the transcripts.

1. `mcp__*whatsapp*__healthcheck` — confirm `auth_state: paired` and that `transcription` is present.
2. `mcp__*whatsapp*__list_messages` on the self-chat JID (the user's own number, e.g. `<phone>@s.whatsapp.net`; the bridge may report it merged with a `@lid` JID — either works), `limit: 40`.
3. Read every `type: "voice"` message since the last journal entry. Each carries a `voice_note_transcript` field — use it verbatim. If a note has no transcript yet, call `download_media` and note the gap.
4. Extract mood, what happened, self-reported habits, people named, gratitudes the user already stated, and the floor language they used themselves. Build the interview and the `## Today` / `## Journal` sections on top of that.
5. **Ask only about what the voice notes did NOT cover.** Open by reflecting back what you heard, then ask your follow-ups. Do not make the user re-narrate a day they already narrated into their phone.

If the self-chat has no voice notes since the last entry, say so plainly and run the normal opener. Never skip this pull silently: with the toggle on, a `/journal` that didn't check the self-chat is broken.

**0d. WhatsApp + iMessage since your last journal (gated on `data_sources.whatsapp_24h` / `imessage_24h`).** Prefer an MCP-INDEPENDENT on-demand reader over the live MCPs — a per-session stdio MCP for every channel adds memory pressure, and the journal should still get message context when those MCPs are not loaded. If a reader script exists in the vault (e.g. `Meta/scripts/journal-messages-fetch.py`), run it for the WHOLE gap since the last entry, not just 24h:

```
python3 "Meta/scripts/journal-messages-fetch.py" --since <last_journal_date> --until <target_date>
```

`--since` should default to the most recent journal entry's creationDate (scan the last two monthly folders; `journal-index.json` may be a stale cache) so it spans EVERY un-journaled day. The reader reads the on-disk channel exports (kept fresh by a scheduled export job), prints a per-contact, per-day digest grouped by channel, applies `whatsapp_filters.exclude_chats` / `imessage_filters.exclude_chats`, and ends with an HONEST freshness footer: the newest message actually on disk per channel, plus a warning if the WhatsApp bridge looks unlinked or iMessage looks stale. Read the digest and surface load-bearing threads (family, co-founder, partner, vendor commitments, conflict/repair, emotionally-loaded exchanges) into the interview and the `## Today` section. Quote verbatim what the user already lived through; never paraphrase the painful stuff away. If the footer flags the bridge unlinked, TELL the user to re-link rather than silently presenting stale data as current.

**Fallback:** if no reader script exists but a WhatsApp/iMessage MCP IS connected this session, use the legacy same-day path (`mcp__whatsapp__list_chats` / `mcp__imessage__list_chats`, `limit: 15`, read load-bearing threads, `[Voice note] <transcript>` inline). The reader is preferred because it is MCP-independent and covers the full gap, not just 24h.

**0f. Calendar** (gated on `data_sources.calendar: on`). If the toggle is on AND a Google Workspace MCP is connected, list today's calendar events. Apply `calendar_filters.include_calendars` (empty list = all calendars). Note who was met, when, and any block titles that name commitments. Otherwise skip silently.

**0g. Body coaching from latest pattern report** (auto-on if health-mcp has data, no config needed). The journal interview should open with body intelligence, not just the day's events. Two-part fetch:

1. **Yesterday's body track.** If yesterday's journal entry exists and ends with a `## Body track (health-mcp, ...)` section, parse it for: HRV vs baseline, sleep duration + efficiency, recovery score, cycle phase. Also note yesterday's Floor.
2. **Latest Health Pattern Report.** Find the most recent `🏠 Home/Health Pattern Report YYYY-MM-DD.md` (or `Home/Health Pattern Report ...` for non-emoji vaults). Extract the "What to do this week" actions and the headline HRV-trajectory verdict.

**Surface as ONE opening coaching prompt before the interview starts.** Format:

> "Before today's check-in — your body is telling me something I want to ask you about.
> 
> Yesterday's body track: HRV X ms (Δ% vs baseline), sleep Yh Zm, recovery score W. Floor: {floor}.
> 
> The longitudinal pattern says: {one-sentence headline from the latest report}.
> 
> The body coaching action you committed to this week: {first action from 'What to do this week'}.
> 
> Three questions before we go into the day:
> 1. How's the body actually feeling right now, in your own words?
> 2. The {floor} you tagged yesterday — did it carry into this morning?
> 3. Did you hold the {action} commitment yesterday? Honest answer."

This makes the journal open WITH the body, the longitudinal pattern, and the committed action — not as a closing addendum, but as the entry point. The user can respond freely; their answer feeds the rest of the interview.

**Health & Body panel triggers** (mid-interview). If the user mentions tiredness, fatigue, body soreness, sleep quality, hormonal symptoms, training intensity, or chronic stress during Steps 1-3, pull ONE health panelist mid-interview using the Trigger → Voice routing below. Same one-sentence rule: their voice, then return.

| Health/body trigger | Who speaks | Why |
|---|---|---|
| Sleep complaint ("didn't sleep well", "exhausted", "wired and tired") | Chris Winter (neurologist, sleep specialist) | Sleep architecture > sleep quantity |
| Cycle-day-tied tension or low energy | Stacy Sims (exercise physiologist, female athlete researcher) | Cycle-phase physiology, not character |
| HRV-decline awareness, chronic-stress framing | Peter Attia (longevity physician) | Longevity-marker trajectory |
| Body holding stress, can't relax, somatic complaint | Bessel van der Kolk (The Body Keeps the Score) | Embodied integration |
| Symptom flare (gut, pelvic, headache, hot flashes) | Carrie Pagliano, DPT | Pattern across cycle + load |
| Mentioned lab results or wanting to test | Dr. Elizabeth Boham (functional medicine) | Root-cause framing |

Skip 0g silently if health-mcp has no data or no Health Pattern Report exists yet. Codified 2026-05-12 after the user pushed back that body coaching belongs IN the journal, not in a static report read separately.

**Why some sources are opt-in:** iMessage, WhatsApp, and Calendar see private conversations and meetings. The user should consent explicitly per vault, not by default. The other three (RescueTime, Session Captures, Today's activity) read your own data and are on by default. Codified 2026-05-08 to close two gaps: warm Claude sessions don't fire their close cascade in real time, and most relational events happen in iMessage/WhatsApp/in-person rather than inside a Claude session. The journal must see the whole day, but the user opts in per vault to the cross-platform pulls.


**Show them the seeds at the very top of the conversation** before asking the check-in question:

> "Before we start — here's what you said today across your sessions. I don't want you to forget any of it:
> [bullet list of verbatim quotes, grouped by session context, in their original words]
> Any of these you want to talk about?"

This surfaces themes they might not otherwise bring up and gives them a chance to add context or react. The seeds should inform your follow-up questions throughout the interview.

**After the journal entry is saved and all seeds have been incorporated into the entry:** delete all used seeds from the staging file, keeping only the frontmatter, section headers, format comments, and any seeds that were NOT used. Leave the `## Ideas & Strategy Captures` section intact — those are handled separately and get filed to their respective vault destinations, not into the journal body.
