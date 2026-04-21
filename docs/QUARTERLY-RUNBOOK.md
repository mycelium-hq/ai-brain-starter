# Quarterly Vault Runbook

A detailed runbook for the quarterly health check your vault needs every 3 months. Goes deeper than the monthly `vault_maintenance.py` scan — this one touches your narrative documents, not just mechanical hygiene.

Use this as the prompt body for a Claude Code scheduled task, or run it manually when you notice your vault feels "off."

## When to run

- Every quarter (1st of Jan/Apr/Jul/Oct).
- When your `About Me.md` or domain summaries feel out of date.
- When your vault map counts look wrong.
- After a major vault reorg.

## The 10 steps

### 1. About Me refresh

Find the latest 3 monthly summary files. They may live inside month folders (`Journals/April 2026/2026-04 Monthly Summary.md`) OR at the journals root (`Mar. 2026 Monthly.md`). If fewer than 3 monthlies exist for the current quarter, substitute the two most recent weekly summaries.

Update the "Then vs. Now" section of `Meta/About Me.md` with any new patterns, identity shifts, or framework changes. Don't rewrite — just append a dated subsection.

### 2. Vault map refresh

Run `.md`-only file counts for each top-level folder, plus any major recursive counts (e.g. a `Notes/` folder with subfolders). Update your root `CLAUDE.md` vault map if drift exceeds 10%. Add a footer line: `*Counts updated YYYY-MM-DD (quarterly maintenance).*`

### 3. Current Priorities sync

Read `Meta/Last Session.md`, `Meta/Open Loops.md`, and `Meta/Current Priorities.md`. Flag stale items at the bottom of Current Priorities: `Possibly stale: [items]`. ALSO close any Open Loops items that Current Priorities marks as done (a common drift — priorities move faster than loop files).

### 4. Domain Summaries drift check

For each domain summary (one per top-level content folder):

- Auto-flag if `last_updated` is > 60 days old.
- Auto-flag if `files_in_domain` frontmatter drifts from actual count by > 20%.
- Mechanically update `files_in_domain` and `last_updated` — these are safe.
- Do NOT rewrite prose narrative. That needs a real work session. Instead, add a `stale_prose: true` frontmatter flag and a warning banner at the top of the file pointing to what's outdated. Log a Claude To-do to rewrite.

### 5. Decision Log outcomes

For decisions older than 30 days with blank Outcome fields, append: `⚠️ Outcome not yet recorded — review this quarter`. If all decisions are newer than 30 days, note that in the report (no action needed).

### 6. Graph health + trend

Run your unresolved-links check (e.g. `obsidian unresolved | wc -l` if using the Obsidian CLI). Append a row to `Meta/unresolved-links-trend.tsv`:

```
date	unresolved_count	delta_from_last	notes
2026-04-21	1436	baseline	first baseline
2026-07-21	1502	+66	+4.6% — acceptable
```

Flag in the report if delta > +10%.

### 7. CRM spot check — bulk-import staleness detection

Pull 5 random `priority: high` contacts (seed the RNG on the date for reproducibility within a day). Check each for a common bulk-import artifact pattern:

- `status: unknown` AND
- blank `last_interaction` AND
- `person_journal_mention_count: 0` (if you track this)

Contacts matching all three are false-positive high-priority — they came in from a CSV import with a default priority and nobody ever touched them. Either downgrade priority or add a "Cold — no logged interaction since [source] import [date]" banner to the body.

### 8. Wikilink Reference regeneration + delta

Regenerate `Meta/Wikilink Reference.md` with a script that:

- Scans all `.md` files
- Excludes: `AI Chats/`, `Journals/`, `Daily Logs/`, `Archive/`, `.git/`, `.claude/`, `.obsidian/`, `Pics/`, `Templates/`, `graphify-input/`, `graphify-out/`
- Parses aliases from YAML frontmatter (array form `[a, b]`, list form `- a\n- b`, and inline form `a, b`)
- Groups by folder, alphabetical within

After write, append a delta row to `Meta/wikilink-ref-trend.tsv`:

```
date	note_count	new_notes	deleted_notes
```

If `new_notes - deleted_notes > 50`, flag as "likely untagged import" — that many notes don't usually appear in a single quarter naturally.

### 9. Missing monthly summary check

If the current run is the first of a new quarter, verify that last quarter's final month has a monthly summary file. Example: running in July → check for `Journals/June YYYY/YYYY-06 Monthly Summary.md`. If missing, append a Claude To-do: `Generate {month} monthly summary (weeklies exist, monthly missing)`.

### 10. Cadence auto-review

Count weekly summaries generated since the last quarterly run. If > 12 (i.e. > 3 months cadence gap — the task has been running less often than intended), consider switching the scheduled task to monthly cadence and note the change in the report.

## Report format

Save to `Meta/Last Session.md`, appended BELOW any aggregator region. **This matters:** if you use `aggregate-sessions.py`, it overwrites everything between `<!-- aggregate-sessions:BEGIN -->` and `<!-- aggregate-sessions:END -->` markers. Append your quarterly report below the legacy section (or below the END marker if no legacy section exists) so the next session-end hook doesn't erase it.

Report template:

```markdown
## Quarterly Maintenance — YYYY-MM-DD

### Mechanical updates
| Target | Before | After | Notes |
|---|---|---|---|
| ... | ... | ... | ... |

### Findings to review
- ...

### Trends
- Unresolved links: prev → now (delta)
- Wikilink Reference notes: prev → now (new / deleted)
```

## Lessons worth codifying in your own runbook

These are the gotchas that bit us while building this. Save yourself the time:

1. **Append below the aggregator region, not inside it.** Anything you write between the BEGIN/END markers gets overwritten on next session close.
2. **CRM `priority: high` alone lies.** Always cross-check with `status` + `last_interaction` + journal-mention count. Bulk CSV imports default everyone to high priority.
3. **Domain summary frontmatter drift is silent.** `files_in_domain: 14` sitting in a file that now has 91 files is a sign the narrative is also out of date. Use the drift as your rewrite trigger.
4. **Flag, don't rewrite prose.** Auto-rewriting narrative during a scheduled task produces bland, lossy summaries. Better: flag with `stale_prose: true` + warning banner, log a to-do, let a real work session do the rewrite.
5. **Script blocked by your own hooks?** If you have a `vault-command-nudges` style hook that blocks `grep`/`find`/`git add -A`, prefix your runbook's shell calls with its bypass env var (e.g. `VAULT_VALIDATOR_BYPASS=1`).
6. **Trend files beat spot counts.** A single "unresolved: 1,436" number means nothing. A TSV with date + count + delta tells you whether the vault is degrading.
7. **`pathlib.rglob` through emoji paths breaks on macOS.** Use `glob.glob(recursive=True)` when your folders use emoji prefixes like `📓 Journals/`.
8. **Bias random spot checks toward high-priority items.** A random 5 out of 280 contacts rarely surfaces real problems. 5 random `priority: high` contacts surfaces more signal per read.
