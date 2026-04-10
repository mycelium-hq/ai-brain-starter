---
name: meeting-todos
description: Extract action items from a meeting note and add them to your to-do list. Separates your tasks from others' tasks. Shows a preview before writing anything. Trigger: /meeting-todos
---

# Meeting → To-Do Extractor

After a meeting, pull action items from the transcript or notes and update your to-do file.

## Trigger

`/meeting-todos` — optionally followed by a date or title:
- `/meeting-todos` → uses the most recent meeting note
- `/meeting-todos 2026-04-09` → finds meeting from that date
- `/meeting-todos Tech Sync` → finds meeting matching that title

## Step 1 — Find the meeting note

Check the user's meeting notes folder (from their CLAUDE.md vault map). If the user has multiple meeting note locations (e.g. personal + team vault), check both.

Use the most recently modified `.md` file with `type: meeting` in frontmatter, or the one matching the user's argument.

Tell the user which file you found before proceeding.

## Step 2 — Read the meeting

Read the full meeting note. It may contain:
- A **Notes** or **Summary** section (structured — prioritize this)
- A **Transcript** section (raw — extract from this if no summary exists)

Transcripts may be in any language — extract faithfully.

## Step 3 — Extract action items

**Your tasks** — anything where the user was directly assigned, volunteered, or is the one with context to act:
- "I'll send them..."
- "We'll figure out X" (where they're the decision-maker)
- "I said I'd do..." / "me toca..." / "voy a..."
- Something they need to research and report back

**Others' tasks** — anything assigned to someone else — list these separately for visibility but do NOT add to the user's to-do.

**Open questions / decisions** — anything left unresolved that needs a follow-up conversation.

## Step 4 — Confirm before writing

Show a preview:

```
## From: [Meeting Name] — [Date]

### Your action items (going to to-do):
- [ ] [task 1 — specific and contextualized]
- [ ] [task 2]

### Others' tasks (not going to to-do — FYI only):
- [Name]: [task]

### Open questions:
- [item]

Add these to your to-do? (yes / no / edit first)
```

**Wait for confirmation before writing anything.**

## Step 5 — Update to-do

File: the user's main to-do file (check CLAUDE.md — typically `Home/✅ Get to-do.md` or similar).

Rules:
- Read the file first
- Add a new dated section:

```markdown
## 📋 From [Meeting Name] — [Date]

- [ ] [task 1]
- [ ] [task 2]
```

- Place urgent items near the top, others at the bottom
- Do NOT duplicate tasks already in the file
- Do NOT delete or reorder anything existing
- Update `updated:` in frontmatter to today if it exists

## Step 6 — Add summary to meeting note (optional)

If the meeting note has no structured summary, offer to add one above the Transcript section:

```markdown
## Summary

**Date:** [date]
**Key decisions:** [bullet points]
**Your action items:** [bullet points]  
**Others' action items:** [bullet points]
**Next meeting:** [if mentioned]
```

Ask before writing.

## Rules

- Always confirm before writing
- Be specific: "Research optimal WhatsApp delay time for Colombia" not "Do research"
- Include context in the task: "Discuss referral API payload with John (what data to send when hotel can't take an event)"
- If a meeting had no clear action items for the user, say so — don't invent tasks
- Flag anything time-sensitive: add ⚠️ if they said "today" or "tomorrow"
- **NEVER fail silently.** If the meeting file can't be found or read, say so immediately
