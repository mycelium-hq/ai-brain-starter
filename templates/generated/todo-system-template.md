---
type: template
description: Complete to-do system with priority tiers, inline fields, done archive, stale decay, and auto-refreshing views
install_target: "To-dos/"
---

# To-do System Template

A prioritized task management system for Obsidian with Dataview integration. Includes a main to-do file, auto-refreshing weekly view, and delegation tracker.

## What this installs

| File | Purpose |
|------|---------|
| `To-dos/Get to-do.md` | Main personal to-do list with P1/P2/P3 tiers |
| `To-dos/This Week.md` | Auto-pulls all P1 items via Dataview (never needs manual refresh) |
| `To-dos/Waiting On.md` | Tracks delegated items and external blockers |

## Requirements

- [Dataview](https://github.com/blacksmithgu/obsidian-dataview) plugin installed and enabled

---

## File 1: Get to-do.md

```markdown
---
created: {{date}}
updated: {{date}}
type: meta
last_updated: {{date}}
---

# To-dos

> **What lives here:** Your personal tasks. If you have a shared team to-do list, link to it at the bottom rather than duplicating items.

## Views

| View | What it shows |
|------|---------------|
| [[This Week]] | Auto-pulls all P1s via Dataview |
| [[Waiting On]] | Delegated items + external blockers |

## Jump to section

- [[#🔴 Priority 1 (this week / deadline / blocker)]]
- [[#🟡 Priority 2 (this sprint)]]
- [[#🟢 Priority 3 (backlog)]]
- [[#✅ Done Archive]]

---

## 🔴 Priority 1 (this week / deadline / blocker)

<!-- Group P1 items by context (e.g., "Client deadline", "Conversations this week", "Blockers"). Every task needs [area::] and [priority::] inline fields. -->

**Example group**
- [ ] Example task with a hard deadline [area:: work] [priority:: 1] [due:: 2026-01-15]

---

## 🟡 Priority 2 (this sprint)

<!-- Items you want done this sprint but that won't cause a crisis if they slip a few days. -->

- [ ] Example sprint task [area:: work] [priority:: 2]

---

## 🟢 Priority 3 (backlog)

<!-- Good ideas, someday tasks, low-urgency maintenance. Review monthly. -->

- [ ] Example backlog item [area:: tools] [priority:: 3]

---

## How to use this file

Every task has **Dataview inline fields** at the end of the line:

| Field | Values | Required? |
|-------|--------|-----------|
| `[area:: X]` | Any workstream (work, writing, tools, people, health, etc.) | **Yes** |
| `[priority:: 1-3]` | 1 = this week / deadline / blocker. 2 = this sprint. 3 = backlog | **Yes** |
| `[due:: YYYY-MM-DD]` | Any date | If deadline exists |

**How to assign priority (three questions, in order):**
1. **Does it have a hard deadline this week?** = `priority:: 1`
2. **Is someone else blocked waiting on this?** Bump up one level
3. **Does it move a top goal?** = `priority:: 1` or `2`. Neither = `priority:: 3`

**Tiebreaker:** "Which one, if I skip it today, creates a problem I can't fix tomorrow?"

**Done archive:** When tasks are checked off, move them to the Done Archive below during weekly reviews. Keeps active sections clean.

**Lint rule:** Every `- [ ]` line MUST have `[area::]` and `[priority::]`. Claude checks for missing fields every time it touches this file and fixes them before saving.

**Stale item rule (enforce during weekly reviews):** Any open item older than 14 days with no `[due::]` field gets flagged. Ask: "Still relevant, or should I drop/re-prioritize this?" Items flagged two weeks in a row get archived. This prevents the list from silently growing stale.

---

## ✅ Done Archive

*Completed tasks, organized by period. Newest at top.*

### Week of {{date}}

<!-- Move checked items here during weekly reviews. Format: [x] task description [area:: X] -->
```

---

## File 2: This Week.md

```markdown
---
type: meta
last_updated: {{date}}
---

# This Week

*Auto-pulls P1 items via Dataview. No manual refresh needed. If the list is longer than 10 items, you have too many P1s.*

## 🔴 P1 items

```dataview
TASK
FROM "To-dos/Get to-do"
WHERE !completed AND priority = 1
SORT due ASC
```

## 🟡 P2s due within 7 days

```dataview
TASK
FROM "To-dos/Get to-do"
WHERE !completed AND priority = 2 AND due AND date(due) <= date(today) + dur(7 days)
SORT due ASC
LIMIT 5
```

---

> **How this works**: P1 items auto-populate here via Dataview. If the P1 section has more than 10 items, some of those are P2s pretending to be urgent, go trim them. The P2 section shows only items with a due date in the next 7 days, capped at 5.
```

---

## File 3: Waiting On.md

```markdown
---
type: meta
last_updated: {{date}}
---

# Waiting On

*Tasks delegated or blocked on someone else. Review weekly.*

## Delegated to others

<!-- Add items you've handed off. Include [since:: YYYY-MM-DD] so stale items are visible. -->
- [ ] Example: sent draft to collaborator for review [since:: 2026-01-10]

## Blocked on external

<!-- Things you can't do until someone else acts. -->
- [ ] Example: waiting for API credentials from vendor [since:: 2026-01-08]

## Blocked on self

<!-- Things where YOU are the bottleneck. Be honest. -->
- [ ] Example: need to make a phone call you keep avoiding [since:: 2026-01-12]

---

> **Review cadence**: Check this list every Monday. If something has been here 2+ weeks with no movement, escalate or drop it.
```

---

## Team variant

If you have a shared team to-do list (e.g., in a team vault or shared folder), add these fields to every task:

| Field | Values | Required? |
|-------|--------|-----------|
| `[owner:: Name]` | Who is responsible | **Yes** |
| `[area:: X]` | Which workstream | **Yes** |
| `[priority:: 1-3]` | Same as personal | **Yes** |
| `[due:: YYYY-MM-DD]` | Hard deadline | If exists |

Then create per-person views using Dataview:

```dataview
TASK
FROM "Team/To-dos"
WHERE !completed AND contains(owner, "YourName") AND priority = 1
GROUP BY area
```

**Additional team rules:**
- **Overdue rule:** Items past their `[due::]` date auto-surface in an Overdue view. Flag these at sprint reviews. Overdue items either get a new due date or get dropped with a reason.
- **Stale item rule:** Same 14-day rule as personal. Enforced during weekly team syncs.
- **Done archive:** When a sprint ends, move completed `[x]` items to a Done Archive section at the bottom of the file, grouped by sprint or date range. Keeps active sections clean while preserving a record of what shipped.
