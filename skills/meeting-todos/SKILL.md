---
name: meeting-todos
description: Extract action items from a meeting note and add them to the to-do list. Separates your tasks from others' tasks. Trigger: /meeting-todos. Do NOT use for general task management, journaling, or pulling full meeting transcripts (use the meeting workflow for that).
argument-hint: "[date like 2026-04-09, or meeting title keyword — omit for most recent]"
---

# Meeting → To-Do Extractor

After a meeting, pull action items from the transcript/notes and update your to-do file.

## Trigger

`/meeting-todos` — optionally followed by a meeting title or date, e.g.:
- `/meeting-todos` → uses the most recent meeting note
- `/meeting-todos 2026-04-09` → finds meeting from that date
- `/meeting-todos Team Sync` → finds meeting matching that title

## Step 1 — Find the meeting note

Check these locations for the most recent (or matching) meeting note:
- `[VAULT]/Meeting Notes/` (or wherever meeting notes live in this vault)
- Any team vault meeting notes folder if configured

If the user specified a date or title, find the matching file. If no argument, use the most recently modified file.

Tell the user which file you found before proceeding.

## Step 2 — Read the meeting

Read the full meeting note. It may contain:
- A **Notes** or **Summary** section (structured — prioritize this)
- A **Transcript** section (raw — extract from this if no summary)

## Step 3 — Extract action items

From the content, identify:

**Your tasks** — anything where:
- You were directly assigned ("You will...", "I'll...", your name + action)
- You volunteered ("I'm thinking...", "let me...")
- It requires your decision or follow-up ("we need to define X" where you're the one with context)
- You said you'd research or provide something

**Others' tasks** — anything assigned to someone else — list these separately for visibility but DO NOT add to your to-do.

**Decisions pending** — anything that was left unresolved and needs a meeting or decision soon.

## Step 4 — Confirm before writing

Show the user a preview:

```
## From: [Meeting Name] — [Date]

### Your action items (going to to-do):
- [ ] [task 1]
- [ ] [task 2]

### Others' tasks (not going to to-do — just FYI):
- [Name]: [task]

### Open questions / decisions pending:
- [item]

Shall I add these to your to-do? (yes/no, or edit first)
```

Wait for confirmation before writing.

## Step 5 — Update to-do

Find the to-do file: look for a file named `✅ Get to-do.md`, `TODO.md`, or similar in the vault root or `🏠 Home/` folder.

Rules:
- Read the file first to understand current structure
- Add a new section or append to the most relevant existing section
- Use this format for the new items:

```markdown
## 📋 From [Meeting Name] — [Date]

- [ ] [task 1]
- [ ] [task 2]
```

Place it after `## 🔥 Urgent / Active` if the tasks are urgent, or at the bottom if they're not.

- Do NOT duplicate tasks already in the file
- Do NOT delete or reorder existing tasks
- Update the `updated:` field in frontmatter to today's date if it exists

## Step 6 — Save meeting summary (optional)

If the meeting note did NOT already have a structured summary, add one at the top of the meeting file (above the Transcript section):

```markdown
## Summary

**Date:** [date]
**Attendees:** [names]
**Key decisions:** [bullet points]
**Your action items:** [bullet points]
**Others' action items:** [bullet points]
**Next steps:** [bullet points]
```

Ask the user if they want this added before writing.

## Rules

- Always confirm before writing to to-do
- Transcripts in any language are fine — extract in the language of the meeting, or match the user's preference
- Be specific: "Research optimal response time for Colombia market" not "Do research"
- Include context in the task where helpful: "Discuss referral API payload with John (what data to send when hotel can't take event)"
- If a meeting had no clear action items, say so — don't invent tasks
- **NEVER fail silently.** If the meeting file doesn't exist or can't be read, tell the user immediately
