---
creationDate: <% tp.date.now("YYYY-MM-DD") %>
type: theme
aliases: []
---

**Floor:**
**Journal entries:** | **Daily files:** | **Chat transcripts:**
**Energy:**

<% tp.file.cursor() %>

## How it shows up
-

## The interesting part


## From your journals


## Connected


## All Entries

```dataviewjs
const name = dv.current().file.name;
const linked = dv.pages(``)
  .where(p => !p.file.path.includes("_meta"))
  .sort(p => p.creationDate || p.file.mtime, "desc");

const rows = linked.map(p => {
  const date = p.creationDate
    ? String(p.creationDate).slice(0,10)
    : p.file.mtime.toFormat("yyyy-MM-dd");
  const folder = p.file.folder.split("/").pop();
  return [p.file.link, date, folder];
});

dv.paragraph(`**${rows.length} connected files**`);
dv.table(["File", "Date", "Source"], rows);
```
