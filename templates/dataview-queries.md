---
type: meta
description: Reusable Dataview queries for an AI-powered Obsidian vault
---

# Dataview Query Library

Copy any of these into a note and Dataview will render them live. Requires the [Dataview](https://github.com/blacksmithgu/obsidian-dataview) plugin.

These queries assume the vault structure produced by `/setup-brain`:

- **`Journals/`** — daily journal entries with `creationDate` and `floor` frontmatter
- **`Notes/`** — concept and theme notes
- **`CRM/`** — contact cards with `relationship`, `priority`, `status`, `last_interaction`, `next_step` frontmatter
- **`Writing/`** — drafts and published essays
- **`AI Chats/`** — exported AI conversations (with `concepts:` array in frontmatter, populated by graphify)

Replace folder names with your own vault structure. Replace `[[Concept]]` placeholders with concepts you actually want to query.

---

## Journal entries by concept

Find every journal entry that mentions a concept. Change the wikilink to explore any concept across your entire history.

```dataview
TABLE creationDate AS "Date", file.name AS "Entry"
FROM "Journals"
WHERE contains(file.outlinks, [[Fear]])
SORT creationDate ASC
```

---

## Journal entries for a concept — by year

See how a concept evolved over time.

```dataview
TABLE dateformat(creationDate, "yyyy") AS "Year"
FROM "Journals"
WHERE contains(file.outlinks, [[Courage]])
GROUP BY dateformat(creationDate, "yyyy")
```

---

## Journal entries tagged with TWO concepts

Find entries where two concepts appear together — the moments of intersection are usually the most interesting.

```dataview
TABLE creationDate AS "Date"
FROM "Journals"
WHERE contains(file.outlinks, [[Fear]]) AND contains(file.outlinks, [[Courage]])
SORT creationDate ASC
```

---

## Most-connected journal entries

Entries that touch the most concepts. These are the high-density days worth re-reading.

```dataview
TABLE length(file.outlinks) AS "Concepts tagged"
FROM "Journals"
SORT length(file.outlinks) DESC
LIMIT 20
```

---

## Journal entry length over time (diagnostic)

Track whether your entries are getting shorter or longer. Useful for detecting drift.

```dataview
TABLE length(file.content) AS "Length", floor AS "Floor"
FROM "Journals"
WHERE floor != null
SORT length(file.content) DESC
LIMIT 20
```

---

## Journals by year — full count

```dataview
TABLE rows.file.name AS "Entries"
FROM "Journals"
GROUP BY dateformat(creationDate, "yyyy") AS "Year"
SORT rows[0].creationDate ASC
```

---

## Concept nodes — recently modified

```dataview
TABLE file.mtime AS "Modified"
FROM "Notes"
SORT file.mtime DESC
LIMIT 20
```

---

## All notes linked to a concept (local graph alternative)

```dataview
LIST
FROM [[Courage]]
SORT file.name ASC
```

---

## CRM — Active high-priority contacts

```dataview
TABLE relationship AS "Role", company AS "Company", last_interaction AS "Last Contact"
FROM "CRM"
WHERE priority = "high" AND status = "active"
SORT file.name ASC
```

---

## CRM — Needs follow-up

Anyone with a `next_step` field in their frontmatter.

```dataview
TABLE relationship AS "Role", next_step AS "Next Step"
FROM "CRM"
WHERE next_step != "" AND next_step != null
SORT file.name ASC
```

---

## CRM — Stale contacts (no contact in 30+ days)

```dataview
TABLE last_interaction AS "Last Contact", relationship AS "Role"
FROM "CRM"
WHERE status = "active" AND date(today) - date(last_interaction) > dur(30 days)
SORT last_interaction ASC
```

---

## AI conversations by concept

Search across your AI conversation history. Requires AI Chats notes to have a `concepts:` frontmatter array (graphify can populate this).

```dataview
TABLE file.name AS "Conversation"
FROM "AI Chats"
WHERE contains(concepts, "Strategy")
SORT file.name ASC
```

---

## AI conversations by month

Volume over time.

```dataview
TABLE length(rows) AS "Count"
FROM "AI Chats"
GROUP BY regexreplace(file.name, "^(\d{4}-\d{2}).*", "$1") AS "Month"
SORT key ASC
```

---

## AI conversations — most concepts tagged

The richest, most multi-dimensional conversations.

```dataview
TABLE length(concepts) AS "Concepts", concepts AS "Tags"
FROM "AI Chats"
SORT length(concepts) DESC
LIMIT 20
```

---

## Cross-source concept search (Journals + AI Chats)

See a concept across both journals AND AI conversations together.

```dataview
TABLE file.folder AS "Source", file.name AS "Entry"
FROM "Journals" OR "AI Chats"
WHERE contains(file.outlinks, [[Courage]]) OR contains(concepts, "Courage")
SORT file.name ASC
LIMIT 30
```

---

## All drafts in progress

```dataview
TABLE file.mtime AS "Last edited", status AS "Status"
FROM "Writing"
WHERE status = "draft" OR status = "in-progress"
SORT file.mtime DESC
```

---

## Mentions block (CRM contact pages)

Drop this on every CRM contact page so the page automatically lists every place they're mentioned across your vault. Requires the contact's name to be wikilinked from other notes (`[[Person Name]]`).

```dataview
TABLE WITHOUT ID
  link(file.link) AS "Mention",
  file.folder AS "Source"
FROM [[]]
WHERE file.path != this.file.path
SORT file.mtime DESC
LIMIT 30
```

---

## To-do system queries

These queries work with the inline-field to-do system documented in `docs/TODO_SYSTEM.md`. Every task needs `[owner:: Name] [area:: X] [priority:: 1-3]` at the end of the checkbox line.

### My tasks (filter by person, sorted by priority)

```dataview
TASK
FROM "Team/Home/Team To-dos"
WHERE !completed AND contains(owner, "Alice") AND priority = 1
GROUP BY area
```

### All tasks by area

```dataview
TASK
FROM "Team/Home/Team To-dos"
WHERE !completed
GROUP BY area
```

### Overdue tasks

```dataview
TASK
FROM "Team/Home/Team To-dos"
WHERE !completed AND due AND due < date(today)
SORT due ASC
```

### Due this week

```dataview
TASK
FROM "Team/Home/Team To-dos"
WHERE !completed AND due AND due >= date(today) AND due <= date(today) + dur(7 days)
SORT due ASC
GROUP BY owner
```

### Waiting on others (delegated items)

Shows tasks owned by others, excluding your own. Replace "Alice" with your name.

```dataview
TASK
FROM "Team/Home/Team To-dos"
WHERE !completed AND contains(owner, "Bob") AND !contains(owner, "Alice")
SORT area ASC
```

### Sprint progress (completed vs remaining)

```dataview
TASK
FROM "Team/Home/Team To-dos"
WHERE completed
GROUP BY area
```

---

## Decision Log queries

If you keep a Decision Log (see `templates/Decision Log.md`), these queries surface patterns over time.

### Decisions by floor (emotional state)

Useful for noticing whether you tend to make important decisions from fear, reason, courage, etc.

```dataview
TABLE floor AS "Floor", stakes AS "Stakes", outcome AS "Outcome"
FROM "Meta/Decisions"
GROUP BY floor
```

### High-stakes decisions, sorted by date

```dataview
TABLE date AS "Date", what AS "Decision", outcome AS "Outcome"
FROM "Meta/Decisions"
WHERE stakes = "high"
SORT date DESC
```

### Open decisions (no outcome filled in yet)

```dataview
TABLE date AS "Date", what AS "Decision", floor AS "Floor"
FROM "Meta/Decisions"
WHERE outcome = "" OR outcome = null
SORT date DESC
```
