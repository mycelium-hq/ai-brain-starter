---
type: template
description: To-do system with capture inbox, prioritized queue, Eisenhower four-quadrant view, optional weighted scoring formula, done archive, stale decay, and auto-refreshing weekly lens
install_target: "To-dos/"
---

# To-do System Template

A two-file to-do system for Obsidian with Dataview integration. One inbox for raw captures, one prioritized queue, and an Eisenhower four-quadrant view rendered at the top of the queue so your top priorities are visible every time you open the file. Also ships an optional weighted scoring formula for users who want more rigor than pure P1/P2/P3 judgment calls.

## What this installs

| File | Purpose |
|------|---------|
| `To-dos/Get to-do.md` | Prioritized personal queue. P1/P2/P3 tiers + four-quadrant Dataview view at top + optional weighted scoring system. |
| `To-dos/From Meetings.md` | Capture inbox. Raw tasks from journal entries, meetings, and sessions land here first, grouped by source. Triaged weekly. |
| `To-dos/This Week.md` | Auto-pulls all P1 items from both files via Dataview (never needs manual refresh). |
| `To-dos/Waiting On.md` | Tracks delegated items and external blockers. |

## Requirements

- [Dataview](https://github.com/blacksmithgu/obsidian-dataview) plugin installed and enabled

## Why two files instead of one

Capture and execution are different modes. Mixing them means every time you open the list, raw inbox clutter distracts you from what actually needs doing. The split keeps `Get to-do.md` clean and actionable, while `From Meetings.md` holds everything you captured during journaling or meetings until you have time to triage. The four-quadrant view at the top of `Get to-do.md` reads from both files, so nothing urgent gets lost just because it lives in the inbox.

## Two prioritization modes: pick one

You can run this template with either:

1. **Pure P1/P2/P3 judgment.** Fast, low-ceremony, no math. Assign priority using the three-question framework below. Best if you trust your gut and hate scoring.
2. **Weighted scoring formula (optional).** Four numeric inputs per task (impact, urgency, effort, commitment), one computed score, and deterministic thresholds map to P1/P2/P3. Best if you find yourself mis-prioritizing, want an auditable reason for each assignment, or have an LLM doing triage for you.

Mode (1) is the default because pure Eisenhower works for most people. Mode (2) is documented below under "Optional: Weighted Scoring System" so you can opt in without rewriting anything. Both modes produce the same `[priority:: 1|2|3]` output, so the four-quadrant view works identically either way.

---

## File 1: Get to-do.md

````markdown
---
created: {{date}}
updated: {{date}}
type: meta
last_updated: {{date}}
---

# Get to-do

> **Prioritized personal queue.** Every task here has been triaged and placed in P1/P2/P3. Raw captures live at [[From Meetings]]. If you have a team to-do list, link to it at the bottom rather than duplicating items.

---

## 🎯 Four Quadrants — what to do, at all times

*Eisenhower matrix, auto-rendered from every task in [[Get to-do]] and [[From Meetings]].*
*Importance = `[priority::]` (1 = high, 2 = mid, 3 = low). Urgency = `[due::]` within 7 days, or no due date on a P1.*

### 🔴 Q1: DO NOW (Important + Urgent)

```dataview
TASK
FROM "To-dos/Get to-do" OR "To-dos/From Meetings"
WHERE !completed AND priority = 1 AND (!due OR date(due) <= date(today) + dur(7 days))
SORT due ASC
```

### 🟡 Q2: SCHEDULE (Important, Not Urgent)

```dataview
TASK
FROM "To-dos/Get to-do" OR "To-dos/From Meetings"
WHERE !completed AND ((priority = 1 AND due AND date(due) > date(today) + dur(7 days)) OR (priority = 2 AND (!due OR date(due) > date(today) + dur(7 days))))
SORT due ASC
```

### 🟠 Q3: DELEGATE / CUT (Urgent, Less Important)

```dataview
TASK
FROM "To-dos/Get to-do" OR "To-dos/From Meetings"
WHERE !completed AND priority = 2 AND due AND date(due) <= date(today) + dur(7 days)
SORT due ASC
```

### ⚪ Q4: BACKLOG (Neither)

```dataview
TASK
FROM "To-dos/Get to-do" OR "To-dos/From Meetings"
WHERE !completed AND priority = 3
SORT file.ctime DESC
```

### ❓ NEEDS TRIAGE (no priority tag yet)

```dataview
TASK
FROM "To-dos/Get to-do" OR "To-dos/From Meetings"
WHERE !completed AND !priority
SORT file.ctime DESC
```

---

## Views

| View | What it shows |
|------|---------------|
| [[From Meetings]] | Raw capture inbox, needs triage |
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

**How the quadrants work:** the Eisenhower view at top reads `[priority::]` (importance) and `[due::]` (urgency) from every task. P1 with due within 7 days or no due date = Q1 (do now). P1 or P2 without near due = Q2 (schedule). P2 with near due = Q3 (delegate or cut). P3 = Q4 (backlog). Items without `[priority::]` surface as "NEEDS TRIAGE" so nothing gets silently dropped.

---

## Optional: Weighted Scoring System

*Skip this section if the three-question framework above works for you. It does for most people.*

If you find yourself repeatedly mis-prioritizing, want an auditable reason for every assignment, or have an LLM (Claude or similar) doing triage on your behalf, you can upgrade P1/P2/P3 from a judgment call to a deterministic calculation. Every new task gets four inputs; a formula computes a score; thresholds map to priority tiers.

**Four inline fields per task (in addition to `[area::]` and `[due::]`):**

| Field | Scale | Meaning |
|---|---|---|
| `[impact:: 1-5]` | 5 = moves a top goal directly. 1 = nice to have. | Goal alignment |
| `[urgency:: 1-5]` | 5 = today, 4 = this week, 3 = sprint, 2 = month, 1 = someday | Time consequence of delay |
| `[effort:: S\|M\|L]` | S = <30min, M = 1-3hrs, L = half day+ | Execution cost |
| `[commit:: Y\|N]` | Y = promised to someone external (client, teammate, partner) | Integrity weight |

**Formula:** `score = impact*0.40 + urgency*0.30 + (4 - effort_score)*0.15 + commit_bonus*0.75`
(where effort: S=1, M=2, L=3; commit: Y=1, N=0)

**Thresholds:**
- **P1** (execute this week): score ≥ 3.75
- **P2** (this sprint): 2.75–3.74
- **P3** (backlog): < 2.75

Example: a task tagged `[impact:: 5] [urgency:: 4] [effort:: M] [commit:: Y]` scores `5*0.40 + 4*0.30 + (4-2)*0.15 + 1*0.75 = 2.0 + 1.2 + 0.3 + 0.75 = 4.25` → P1.

**Why these weights?** Impact is weighted highest because the single biggest mistake in to-do systems is letting urgent-but-unimportant work crowd out important-but-patient work. Urgency is still significant but not dominant. Effort is inverted (lower effort = bonus toward P1) so a small task with big impact beats a big task with medium impact, which matches how most people actually get unstuck. The commit bonus is a flat boost because breaking commitments has a nonlinear cost (trust damage) that the impact/urgency scales don't capture.

**Calibrate before you trust the numbers.** These weights are a sensible first guess, not evidence. Run this calibration before you rely on the formula:

1. Take 20 existing tasks with known "correct" priorities.
2. Score them manually using the formula.
3. Compare the computed P1/P2/P3 assignments against your gut.
4. If the formula systematically over- or under-rates certain categories (e.g., all your writing tasks come out P1 because `impact` is inflated), adjust the weights or the scale definitions.
5. Only then start using the formula on new tasks.

**When to fall back to pure judgment:** if after two weeks of using the formula your daily execution hasn't actually changed, the formula is plumbing, not value. Go back to P1/P2/P3 gut calls. The four-quadrant view works either way.

**Claude-assisted triage:** if you want Claude to do the scoring when items flow from `From Meetings.md` to `Get to-do.md`, tell Claude: "Triage the capture inbox. Score each new item using the Weighted Scoring System in Get to-do.md. Show me the score and assigned priority before moving the item." Claude computes `[score:: X.X]` and sets `[priority::]` based on the thresholds.

**Back-compat for existing items:** tasks that were written before you opted into scoring keep their current `[priority::]` tag. Only new items need the full four-field set. The four-quadrant view reads `[priority::]` regardless of how it was assigned, so pre-scoring and post-scoring tasks render side by side.

**Done archive:** When tasks are checked off, move them to the Done Archive below during weekly reviews. Keeps active sections clean.

**Lint rule:** Every `- [ ]` line MUST have `[area::]` and `[priority::]`. Claude checks for missing fields every time it touches this file and fixes them before saving.

**Stale item rule (enforce during weekly reviews):** Any open item older than 14 days with no `[due::]` field gets flagged. Ask: "Still relevant, or should I drop/re-prioritize this?" Items flagged two weeks in a row get archived. This prevents the list from silently growing stale.

---

## ✅ Done Archive

*Completed tasks, organized by period. Newest at top.*

### Week of {{date}}

<!-- Move checked items here during weekly reviews. Format: [x] task description [area:: X] -->
````

---

## File 2: From Meetings.md

````markdown
---
created: {{date}}
type: meta
last_updated: {{date}}
---

# From Meetings

> **Capture inbox.** Raw tasks from journaling, meetings, and sessions land here first, grouped by source. Items are NOT prioritized here, they flow to [[Get to-do]] during weekly triage with a `[priority::]` tag assigned.
>
> **Triage cadence:** once a week (e.g., Monday planning), and at session close when captures pile up.
>
> **Move rule:** once an item has a priority, it lives in [[Get to-do]]. This file only holds unfiled captures.
>
> Tasks here still surface in the four-quadrant view on [[Get to-do]] if they already have a `[priority::]` tag, so urgent captures do not get lost while waiting for formal triage.

---

## 📋 From {{example source, e.g., Weekly planning session}} — {{date}}

<!-- Each capture block is grouped under a source header. Examples: "From Journal YYYY-MM-DD", "From 1:1 with Manager YYYY-MM-DD", "From Sprint Retrospective YYYY-MM-DD". -->

- [ ] Example capture that still needs triage [area:: work]
- [ ] Example capture with an assumed priority already [area:: work] [priority:: 2]
````

---

## File 3: This Week.md

````markdown
---
type: meta
last_updated: {{date}}
---

# This Week

*Auto-pulls P1 items from your prioritized queue and your capture inbox via Dataview. No manual refresh needed. If the list is longer than 10 items, you have too many P1s.*

## 🔴 P1 items

```dataview
TASK
FROM "To-dos/Get to-do" OR "To-dos/From Meetings"
WHERE !completed AND priority = 1
SORT due ASC
```

## 🟡 P2s due within 7 days

```dataview
TASK
FROM "To-dos/Get to-do" OR "To-dos/From Meetings"
WHERE !completed AND priority = 2 AND due AND date(due) <= date(today) + dur(7 days)
SORT due ASC
LIMIT 5
```

---

> **How this works**: P1 items auto-populate here via Dataview, including items still sitting in `From Meetings` that already have a priority tag. If the P1 section has more than 10 items, some of those are P2s pretending to be urgent, go trim them. The P2 section shows only items with a due date in the next 7 days, capped at 5.
````

---

## File 4: Waiting On.md

````markdown
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
````

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
