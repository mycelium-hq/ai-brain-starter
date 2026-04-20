---
name: second-brain-mapping
description: Unified vault-mapping pipeline. Extracts structured metadata from every typed file in your vault (books, meetings, people, articles, goals, etc.), optionally runs knowledge-graph extraction, applies wikilinks, and surfaces cross-type insights you can't see from any single file. Zero LLM cost per run for metadata + insights. Use whenever you want to "map your second brain", refresh your vault's queryable index, or discover cross-doc patterns.
trigger: /second-brain-mapping
argument-hint: "[--metadata-only | --insights-only | --dry-run | --force | --type <name>]"
---

# /second-brain-mapping

Your vault is a database. This skill makes it queryable.

## What it does

| Phase | Tool | LLM cost | Always runs? |
|---|---|---|---|
| 1 | `vault-metadata-extract.py` (dispatcher → type-specific extractors) | **0 tokens** | Yes |
| 2 | `/graphify` (optional) | ~100k–1M tokens | No — asks first |
| 3 | Wikilink gaps + interactive apply | ~5k tokens | If graph exists |
| 4 | `vault-insight-engine.py` — cross-type surprise finder | **0 tokens** | Yes |

Phases 1 and 4 are free. Phase 2 is expensive and opt-in. Phase 3 needs interactive approval so it skips gracefully in non-TTY contexts.

## Setup

Run once after cloning ai-brain-starter:

```
/setup-vault-types
```

Interactive wizard asks which doc types you have (journal, book, article, meeting, person, project, podcast, client, etc.) and installs the matching extractors. You can add custom types later by editing `scripts/extractors/schemas.yaml` or running `/setup-vault-types --add <name>`.

## Usage

```bash
/second-brain-mapping                 # full pipeline
/second-brain-mapping --metadata-only # skip graphify + wikilinks, keep insights
/second-brain-mapping --insights-only # only run Phase 4 on existing metadata
/second-brain-mapping --type book     # only process files with `type: book`
/second-brain-mapping --dry-run       # preview without writes
```

## Why this matters

Most PKM tools stop at search. This turns your vault into a queryable database:

- *"Every book I rated 4+ that mentions compound interest"*
- *"Every high-priority contact not touched in 60+ days"*
- *"Every concept that appears in my books AND journals AND writing drafts"*
- *"People whose name co-occurs with low-floor journal entries 60%+ of the time"*

Dataview handles the queries. This skill handles the structured fields that make Dataview precise.

## Steps

Follow in order. Do not skip.

### Step 1 — Context

Run `date` for timestamp. Parse any argument flags.

### Step 2 — Phase 1: vault-metadata-extract (always)

```bash
python3 "$(vault-root)/scripts/vault-metadata-extract.py" $FLAGS
```

Report: X files written, Y already tagged, types with no registered extractor.

### Step 3 — Phase 2: graphify (confirm first)

Check graph state:

```bash
stat -f "%Sm" "$(vault-root)/graphify-out/graph.json" 2>/dev/null || echo "no graph yet"
```

Ask: **"Run graphify? ~100k-1M tokens depending on corpus size. y/N"**

If yes, invoke `/graphify --update`. Read `~/.claude/skills/graphify/SKILL.md` first for the optimization wrappers.

### Step 4 — Phase 3: wikilinks

```bash
python3 "$(vault-root)/scripts/graphify_wikilink_gaps.py"
if [[ -t 0 ]]; then
  python3 "$(vault-root)/scripts/graphify_apply_wikilinks.py"
else
  echo "Non-interactive: wikilink apply skipped. Run manually to review."
fi
```

### Step 5 — Phase 4: insights (always)

```bash
python3 "$(vault-root)/scripts/vault-insight-engine.py" --top 5
```

Read the top 5 findings aloud. Don't summarize — paste the report section verbatim so the user sees the raw signal.

### Step 6 — Summary + cross-type query suggestions

Print a compact summary. Then suggest 2-3 concrete Dataview queries the user could now run based on what got extracted. Examples:

```
You now have 47 books and 264 people. Try these queries on any note:

  // Books you loved that mention a concept:
  TABLE book_author, book_rating_1_5
  FROM "Notes/Books"
  WHERE book_rating_1_5 >= 4
    AND contains(book_themes, "<concept>")

  // High-priority contacts going cold:
  TABLE person_last_journal_iso, person_next_step
  FROM "CRM"
  WHERE person_priority = "high"
    AND person_last_journal_iso < dateformat(date(today) - dur(60 days), "yyyy-MM-dd")
```

## Non-negotiables

- **Zero LLM in extraction.** Every field is regex/enum/count/verbatim section. No paraphrase. No summarization.
- **Always confirm Phase 2.** Graphify is expensive.
- **TTY guard Phase 3.** Non-interactive shells skip apply_wikilinks with a message, never abort mid-file.
- **Report honestly.** If Phase 4 found nothing notable, say so.

## Architecture

```
scripts/
  vault-metadata-extract.py       # entry point
  vault-insight-engine.py         # cross-type surprise finder
  vault-classify-untyped.py       # MiniMax-powered type suggester
  second-brain-mapping.sh         # orchestrator (all four phases)
  extractors/
    _base.py                      # shared helpers
    _dispatcher.py                # type → extractor routing
    schemas.yaml                  # declares fields per type
    journal.py  book.py  person.py  concept.py  article.py
    business.py meeting.py ai_chat.py writing_draft.py
    strategy.py negotiation_prep.py company.py
    daily_log.py talk.py travel.py goal.py
    playbook.py asset.py reference.py
    # Add your own: extractors/<type>.py + entry in schemas.yaml
```

Each extractor module exports `AUTO_FIELDS` and `extract(filepath, body, fm, context) -> ExtractionResult`. The dispatcher auto-discovers any file in `extractors/` that has an `extract` function.

## Adding your own type

1. Edit `extractors/schemas.yaml` to declare your fields
2. Copy an existing extractor (e.g., `book.py`) as template
3. Rename, update logic, save as `extractors/<your_type>.py`
4. Add `type: <your_type>` to any doc that qualifies
5. Run `/second-brain-mapping --type <your_type>` to verify

The framework doesn't care what types exist. It cares that each type declares its fields and ships an extractor.
