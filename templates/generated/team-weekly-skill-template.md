---
name: team-weekly
description: Weekly operational digest for the team. Scans meeting notes, CRM changes, strategy updates, sales activity, and decisions from the past week. Use /team-weekly to generate.
---

# Team Weekly Digest

Generate a weekly operational report by scanning all changes across the team vault in the past 7 days.

## How to Find Recent Files

Use `find "[TEAM_VAULT_PATH]" -name "*.md" -mtime -7` to get files modified in the past 7 days. Read only those files.

## Report Structure

### 1. This Week at a Glance
- Date range (Mon–Sun)
- Files modified, meetings held, new contacts
- One-line summary

### 2. Meetings & Conversations
For each meeting note: who, what, decisions, action items (done vs. open)

### 3. Pipeline & Sales
New leads, outreach sent, deals moved, revenue updates

### 4. Product & Team
What was shipped, blockers, team changes

### 5. Decisions Made
From Decision Log — business decisions this week

### 6. Open Loops
Unresolved heading into next week

### 7. Next Week Focus
Top 3 priorities for next week

## Save Location
- Team vault: `[TEAM_VAULT_PATH]/Strategy/Weekly Digests/YYYY-WXX Team Weekly.md`
- Personal vault: `[PERSONAL_VAULT_PATH]/[PROJECT_FOLDER]/Weekly Digests/YYYY-WXX Team Weekly.md`

## Rules
- Business only — no personal journal content or floor tags
- Name people, meetings, amounts — be specific
- Compare to last week when data exists
- Flag risks: overdue follow-ups, stalled deals, missed deadlines
- NEVER fail silently. Verify both saves.
