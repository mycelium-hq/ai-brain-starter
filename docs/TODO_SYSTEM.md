---
name: todo-system
description: Complete to-do system with Dataview views, priority framework, and focusing lens
---

# To-Do System Architecture

A task management system built on Obsidian + Dataview that scales from solo use to small teams. Every task has machine-queryable inline fields so you can filter by person, area, and priority without leaving your vault.

## The Problem It Solves

A single flat to-do file breaks down when:
- Multiple people need to see only their tasks
- Work spans different areas (fundraising, marketing, product, ops)
- Some items are urgent, others are backlog
- Completed items clutter the active list
- You can't tell at a glance what to work on next

## Architecture

```
Your Vault/
  Home/
    ✅ Get to-do.md          ← personal tasks (writing, health, errands)
    ✅ This Week.md           ← focusing lens: max 7 items, updated Mondays
    ✅ Waiting On.md          ← Dataview-powered: what you've delegated
  Team Vault/ (or Work/ folder)
    Home/
      Team To-dos.md          ← canonical source for all team tasks
      Views/
        My Tasks - [Name].md  ← one per team member
        By Area.md            ← all tasks grouped by workstream
        Sprint Progress.md    ← completed vs total, momentum tracker
        Overdue.md            ← tasks past their due date
        Due This Week.md      ← next 7 days
```

**Key principle:** Team To-dos is the single source of truth. View files are Dataview projections, never copies. Edit tasks in the source file; views update automatically.

## Inline Fields

Every task line gets three required fields appended at the end:

```markdown
- [ ] Write the proposal [owner:: Alice] [area:: sales] [priority:: 1]
```

| Field | Values | Required? | Purpose |
|-------|--------|-----------|---------|
| `[owner:: Name]` | Team member names | **Yes** | Who's responsible |
| `[area:: X]` | Your workstreams (e.g., sales, marketing, product, ops) | **Yes** | Which workstream |
| `[priority:: 1-3]` | 1 = this week / deadline / blocker. 2 = this sprint. 3 = backlog | **Yes** | What to do first |
| `[due:: YYYY-MM-DD]` | Any date | If deadline exists | Hard deadline |

Multi-owner tasks use comma separation: `[owner:: Alice, Bob]`

## Prioritization Framework

Assign priority by asking three questions in order:

1. **Does it have a hard deadline this week?** (meeting, event, external commitment) -> `priority:: 1`
2. **Is someone else blocked waiting on this?** -> Bump up one level
3. **Does it directly move the #1 company/project goal?**
   - Directly -> `priority:: 1` or `2`
   - Indirectly -> `priority:: 2` or `3`
   - Neither -> `priority:: 3`

**Tiebreaker:** "Which one, if I skip it today, creates a problem I can't fix tomorrow?" That one goes first.

**Default:** If unsure, use `priority:: 2`. Claude will re-sort during weekly reviews.

**Target distribution:** ~15 p1 items max. If you have 40+ p1 items, your criteria are too loose. P1 means "if I don't do this in the next 5 days, something breaks."

## View File Templates

### Per-person view (My Tasks - Alice.md)

```markdown
---
creationDate: {{date}}
type: meta
---

# My Tasks - Alice

*Auto-filtered from [[Team To-dos]]. Edit tasks in the source file, not here.*

## 🔴 Priority 1 (this week / deadline / blocker)

\`\`\`dataview
TASK
FROM "Team/Home/Team To-dos"
WHERE !completed AND contains(owner, "Alice") AND priority = 1
GROUP BY area
\`\`\`

## 🟡 Priority 2 (this sprint)

\`\`\`dataview
TASK
FROM "Team/Home/Team To-dos"
WHERE !completed AND contains(owner, "Alice") AND priority = 2
GROUP BY area
\`\`\`

## 🟢 Priority 3 (backlog)

\`\`\`dataview
TASK
FROM "Team/Home/Team To-dos"
WHERE !completed AND contains(owner, "Alice") AND priority = 3
GROUP BY area
\`\`\`
```

### By Area view

```markdown
\`\`\`dataview
TASK
FROM "Team/Home/Team To-dos"
WHERE !completed
GROUP BY area
\`\`\`
```

### Sprint Progress view

```markdown
## Completed

\`\`\`dataview
TASK
FROM "Team/Home/Team To-dos"
WHERE completed
GROUP BY area
\`\`\`

## P1 items remaining (should shrink daily)

\`\`\`dataview
TASK
FROM "Team/Home/Team To-dos"
WHERE !completed AND priority = 1
GROUP BY owner
\`\`\`
```

### Overdue view

```markdown
\`\`\`dataview
TASK
FROM "Team/Home/Team To-dos"
WHERE !completed AND due AND due < date(today)
SORT due ASC
\`\`\`
```

### Waiting On view (Dataview-powered)

Instead of manually tracking what you've delegated, query for tasks owned by others:

```markdown
## [Team member]'s tasks

\`\`\`dataview
TASK
FROM "Team/Home/Team To-dos"
WHERE !completed AND contains(owner, "Bob") AND !contains(owner, "Alice")
SORT area ASC
\`\`\`
```

This is always current because it reads from the canonical source. Manual waiting-on lists drift.

## This Week (the focusing lens)

The most important file in the system. Max 7 items. Updated every Monday.

```markdown
# This Week

**Week of [date]**

## The ONE thing this week
[The single task that, if done, makes everything else easier or unnecessary]

## Must do (5 items max)
- [ ] ...
- [ ] ...

## If time allows
- [ ] ...
```

**How to refresh:** On Monday, delete old items, pick the new top 5 from your personal + team to-dos. If you can't pick just 5, you're trying to do too much.

**Integration with /journal:** If you use the daily-journal skill, add a Monday-specific question: "What's your ONE Thing this week?" The answer populates This Week.md automatically.

## Done Archive

At the bottom of Team To-dos, keep a `## ✅ Done Archive` section. When tasks are completed, move them here (out of the active sections). This keeps active views clean while preserving a motivating record of what got shipped.

```markdown
## ✅ Done Archive

*Completed tasks, organized by sprint/period. Newest at top.*

### [Sprint name] (completed items)

- [x] ~~Task description~~ DONE ([date]) [owner:: X] [area:: Y] [priority:: Z]
```

## Lint Rule (for Claude)

Add this to your CLAUDE.md so Claude auto-fixes missing fields:

> **To-do field lint.** Every `- [ ]` line in Team To-dos MUST have three inline fields: `[owner:: X]`, `[area:: X]`, and `[priority:: N]`. When Claude touches Team To-dos for any reason, scan all unchecked task lines. If any are missing fields, add them using the prioritization framework before saving. When extracting meeting action items via `/meeting-todos`, the skill must add fields to every new task.

## Adding fields to an existing to-do file

If you already have a to-do file with tasks but no inline fields, use a Python script to add them programmatically. The script should:

1. Read the file line by line
2. Track the current section (to infer owner and area from headings)
3. For each `- [ ]` line, append `[owner:: X] [area:: Y] [priority:: N]`
4. Verify the task count before and after (must match)

This is safer than manual editing for files with 100+ tasks. See the ai-brain-starter repo for a reference script.

## How Claude uses the system

- **Session start:** Check `✅ This Week` for current focus
- **"What should I work on?":** Pull p1 items from Team To-dos, sorted by due date
- **Adding tasks:** Always include all three fields
- **Meeting follow-ups:** `/meeting-todos` adds fields to every extracted action item
- **Sprint transitions:** Move completed items to Done Archive automatically
- **Weekly review:** Re-sort priorities using the three-question framework
