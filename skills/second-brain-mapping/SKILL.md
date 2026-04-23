---
name: second-brain-mapping
description: Unified vault-mapping pipeline. Extracts structured metadata from every typed file in your vault (books, meetings, people, articles, goals, etc.), optionally runs knowledge-graph extraction, applies wikilinks, and surfaces cross-type insights you can't see from any single file. Zero LLM cost per run for metadata + insights. Use whenever you want to "map your second brain", refresh your vault's queryable index, or discover cross-doc patterns.
trigger: /second-brain-mapping
argument-hint: "[--metadata-only | --insights-only | --dry-run | --sample [N] | --force | --type <name>]"
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
/second-brain-mapping --sample        # preview 1 file per configured type (cold-start safe)
/second-brain-mapping --sample 3      # preview 3 files per configured type
```

**First-time cold-start?** Run `--sample` first. It processes one file per registered type, shows you the actual extracted fields, and exits without writing anything. If the output looks right, re-run without `--sample` for the full pipeline.

## Why this matters

Most PKM tools stop at search. This turns your vault into a queryable database:

- *"Every book I rated 4+ that mentions compound interest"*
- *"Every high-priority contact not touched in 60+ days"*
- *"Every concept that appears in my books AND journals AND writing drafts"*
- *"People whose name co-occurs with low-floor journal entries 60%+ of the time"*

Dataview handles the queries. This skill handles the structured fields that make Dataview precise.

## Steps

Follow in order. Do not skip.

### Step 1 — Context + per-phase recency check

Run `date` for timestamp. Parse any argument flags.

**Precheck: was `/setup-vault-types` run?** Before anything else, confirm the vault has at least one document-type extractor configured. Without this, Phase 1 runs silently on every file and reports "no extractor registered" for the user's entire vault — a classic cold-start bounce.

```bash
EXTRACTOR_DIR="$(pwd)/scripts/extractors"
EXTRACTOR_COUNT=0
if [[ -d "$EXTRACTOR_DIR" ]]; then
  EXTRACTOR_COUNT=$(find "$EXTRACTOR_DIR" -maxdepth 1 -name '*.py' -not -name '_*' 2>/dev/null | wc -l | tr -d ' ')
fi
if [[ "$EXTRACTOR_COUNT" -eq 0 ]]; then
  echo "No document-type extractors are configured yet."
  echo "Run /setup-vault-types first — that wizard asks which kinds of notes"
  echo "you take (journal, book, meeting, person, etc.) and installs the matching"
  echo "extractors. Then re-run /second-brain-mapping."
  exit 4
fi
```

If this check fails, stop. Do not proceed to any phase. Tell the user to run `/setup-vault-types` and offer to invoke it for them.

Read the state file to see what was done and when:

```bash
STATE_FILE="$(vault-root)/⚙️ Meta/.second-brain-mapping-state.json"
[[ -f "$STATE_FILE" ]] && cat "$STATE_FILE" || echo '{}'
```

State file format (JSON):
```json
{
  "phase_1_metadata":  "2026-04-21T10:02:00-05:00",
  "phase_2_graphify":  "2026-04-21T09:04:26-05:00",
  "phase_3_wikilinks": null,
  "phase_4_insights":  "2026-04-21T10:02:00-05:00"
}
```

`null` means never completed OR killed mid-run. A timestamp means last successful completion.

**Decision rule:**
- If `--force` flag: run everything regardless.
- Else for each phase: if stamp < 4 hours old AND not null → skip (report "Phase X: skipped, ran Y ago"). If stamp is null OR > 4 hours old → run it. Phase 2 (graphify) always confirms before running regardless of stamp.
- Report the plan BEFORE running: "Will run: Phase 3 (null), Phase 4 (>4h). Skipping: Phase 1 (1h ago). OK? y/N"

After each phase succeeds, update its stamp with the current ISO-8601 timestamp. If a phase is killed or errors, leave the stamp untouched so next run sees it as incomplete.

Helper to write stamp (use after each phase):
```bash
python3 -c "
import json, pathlib, datetime
p = pathlib.Path('$STATE_FILE')
d = json.loads(p.read_text()) if p.exists() else {}
d['$PHASE_KEY'] = datetime.datetime.now().astimezone().isoformat(timespec='seconds')
p.write_text(json.dumps(d, indent=2))
"
```

### Step 2 — Phase 1: vault-metadata-extract

If Step 1 decided to skip, skip. Else:

```bash
python3 "$(vault-root)/scripts/vault-metadata-extract.py" $FLAGS
```

On success, stamp `phase_1_metadata`. Report: X files written, Y already tagged, types with no registered extractor.

### Step 3 — Phase 2: graphify (confirm first)

Always ask, even if stamp is fresh. Graphify has its own internal staging and token cost varies wildly.

**Before asking, compute a vault-specific cost estimate.** A generic "~100k-1M tokens" warning is useless to a first-time user. Show them numbers tied to their actual corpus:

```bash
python3 <<'PY'
import os, glob, pathlib, sys

vault = os.getcwd()
SKIP = {"⚙️ Meta", "Archive", ".git", ".obsidian", "graphify-out", "node_modules"}
total_files = 0
total_words = 0
for fp in glob.glob(os.path.join(vault, "**", "*.md"), recursive=True):
    parts = set(fp.split(os.sep))
    if parts & SKIP:
        continue
    total_files += 1
    try:
        with open(fp, "r", encoding="utf-8", errors="ignore") as f:
            total_words += len(f.read().split())
    except Exception:
        pass

# Rough estimate: 1 word ≈ 1.3 tokens input; graphify wrappers reduce ~85% for a full run
# Output is typically 10-15% of input for extraction.
input_tok = int(total_words * 1.3 * 0.15)   # after dedupe + cache + preextract
output_tok = int(input_tok * 0.12)

# Sonnet 4.6 public pricing (as of 2025): $3/M input, $15/M output
cost_usd = (input_tok / 1_000_000) * 3 + (output_tok / 1_000_000) * 15

# Incremental run (cache warm): roughly 10% of cold-start
cold_cost = cost_usd
warm_cost = cost_usd * 0.10

existing = pathlib.Path("graphify-out/graph.json").exists()
mode = "incremental (cache warm)" if existing else "cold start (no cache yet)"
est_cost = warm_cost if existing else cold_cost

print(f"Corpus:   {total_files:,} files · ~{total_words:,} words")
print(f"Mode:     {mode}")
print(f"Tokens:   ~{input_tok:,} input · ~{output_tok:,} output (estimate)")
print(f"Cost:     ~${est_cost:.2f} at Sonnet 4.6 public pricing")
print(f"          (cold start would be ~${cold_cost:.2f}; incremental ~${warm_cost:.2f})")
PY

stat -f "%Sm" "$(pwd)/graphify-out/graph.json" 2>/dev/null || echo "Last graph: none yet"
```

Then ask: **"Run graphify on this corpus? y/N"**

If yes, invoke `/graphify --update`. Read `~/.claude/skills/graphify/SKILL.md` first. On success, stamp `phase_2_graphify`.

**Pricing caveat:** the cost estimate uses public Sonnet rates and graphify's typical compression ratio. Actual cost depends on cache hit rate, chunk granularity, and whether `--mode deep` is used. Treat the number as an order-of-magnitude guide, not a quote.

### Step 4 — Phase 3: wikilinks

If Step 1 decided to skip, skip. Else:

```bash
python3 "$(vault-root)/scripts/graphify_wikilink_gaps.py"
if [[ -t 0 ]]; then
  python3 "$(vault-root)/scripts/graphify_apply_wikilinks.py"
else
  echo "Non-interactive: wikilink apply skipped. Run manually to review."
fi
```

On success (both commands exit 0), stamp `phase_3_wikilinks`. If killed mid-run or errors, DO NOT stamp — next invocation will see it as null and re-run.

### Step 5 — Phase 4: insights

If Step 1 decided to skip, skip. Else:

```bash
python3 "$(vault-root)/scripts/vault-insight-engine.py" --top 5
```

On success, stamp `phase_4_insights`. Read the top 5 findings aloud. Don't summarize — paste the report section verbatim so the user sees the raw signal.

**Scoping to a recent batch.** When Phase 2 only processed a subset of files (e.g. a `/graphify --update` of 200 new files), the same vault-wide patterns dominate every run. To surface insights specific to the batch instead, pass `--scope-files`:

```bash
python3 "$(vault-root)/scripts/vault-insight-engine.py" \
  --scope-files "$(vault-root)/path/to/file-list.txt" \
  --scope-label "batch-YYYY-MM-DD" \
  --top 5
```

File list = one path per line (relative to vault-root or absolute). Findings restrict to those files; baselines still derive from the full vault so "surprise" is measured against your whole history. Without the flag, behavior is unchanged.

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
