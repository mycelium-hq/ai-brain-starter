---
name: setup-vault-types
description: Interactive wizard to configure which document types your vault uses. Asks the user what kinds of notes they take (journals, books, meetings, clients, podcasts, etc.), enables the matching extractors, and scaffolds extractors for custom types. Run once after installing ai-brain-starter, and again whenever you add a new kind of doc. Do NOT use this to run extraction — use /second-brain-mapping.
trigger: /setup-vault-types
argument-hint: "[--add <typename> | --list | --remove <typename>]"
---

# /setup-vault-types

Figure out which doc types belong in this vault, then wire the right extractors.

## Why

`/second-brain-mapping` ships with 18 extractors. You probably don't need all of them. This wizard:

1. Asks what kinds of notes you take
2. Enables the matching extractors
3. Offers to scaffold new extractors for types we don't ship

No "start small" suggestion. You get all the capability for the types you have.

## Steps

### Step 1 — Detect existing types

Scan the vault for files already declaring `type:` in frontmatter:

```bash
cd "$(vault-root)"
grep -rh "^type:" --include="*.md" -I . 2>/dev/null \
  | sed 's/^type:\s*//' | sort | uniq -c | sort -rn | head -30
```

Tell the user: *"Your vault already has these types declared: …"*

### Step 2 — Ask what they take notes on

Present this list, ask user to pick any/all that apply:

```
Core journaling & reflection:
  [ ] journal        — daily reflection / gratitude / mood
  [ ] daily_log      — task-log style (Roam/Capacities daily)
  [ ] goal           — OKRs, quarterly plans, vision docs

Reading & learning:
  [ ] book           — book notes, highlights, reviews
  [ ] article        — saved essays, blog posts, long reads
  [ ] concept        — evergreen concept notes (PKM backbone)

People & relationships:
  [ ] person         — CRM / contact notes
  [ ] meeting        — 1:1s, team syncs, call notes

Creative & publishing:
  [ ] writing_draft  — blog drafts, book chapters, newsletters
  [ ] talk           — speaking engagements, workshops given

Work & business:
  [ ] business       — pitches, memos, client docs, investor updates
  [ ] strategy       — strategic plans, frameworks, bets
  [ ] negotiation_prep — deal prep, BATNA docs
  [ ] company        — entity notes (past/current ventures)
  [ ] ai_chat        — saved AI conversations (Claude, GPT, etc.)
  [ ] playbook       — SOPs, step-by-step guides

Lifestyle:
  [ ] travel         — trip notes, restaurants, places visited

Assets & reference:
  [ ] asset          — brand files, logos, templates
  [ ] reference      — cheat sheets, quick-lookup docs

Custom:
  [+] Add your own type
```

### Step 3 — Install selected extractors

For each checked type, symlink its extractor into the vault's `scripts/extractors/` dir. Leave unchecked types uninstalled — no wasted files.

```bash
VAULT="$(vault-root)"
STARTER="$HOME/.claude/skills/ai-brain-starter"  # or wherever it's installed
for type in ${SELECTED_TYPES[@]}; do
  ln -sf "$STARTER/scripts/extractors/$type.py" "$VAULT/scripts/extractors/$type.py"
done
# Always install base + dispatcher
ln -sf "$STARTER/scripts/extractors/_base.py" "$VAULT/scripts/extractors/_base.py"
ln -sf "$STARTER/scripts/extractors/_dispatcher.py" "$VAULT/scripts/extractors/_dispatcher.py"
ln -sf "$STARTER/scripts/extractors/schemas.yaml" "$VAULT/scripts/extractors/schemas.yaml"
```

### Step 4 — Custom type flow (if user picks "Add your own")

Prompt for:
- Type name (snake_case, e.g., `podcast_episode`, `client_project`)
- 3-8 fields they'd want to extract (e.g., for `podcast_episode`: `guest_name`, `episode_number`, `record_date_iso`, `topics`, `pull_quotes_verbatim`)

Generate the extractor scaffold:

```python
# scripts/extractors/<typename>.py
from _base import count_words, iso_date_from, extract_section, wikilinks_in, ExtractionResult

AUTO_FIELDS = ("<field1>", "<field2>", ...)

def extract(filepath, body, fm, context):
    fields = {
        "<field1>": ...,  # TODO: user fills in extraction logic
        "word_count": count_words(body),
    }
    return ExtractionResult(fields, AUTO_FIELDS, auto_fields=AUTO_FIELDS)
```

Also append the new type to `schemas.yaml`:

```yaml
<typename>:
  folder_hint: "<user-provided>"
  fields:
    - <field1>
    - <field2>
    ...
```

Tell the user: *"I scaffolded the extractor. Open `scripts/extractors/<typename>.py` and fill in the regex/section-parsing logic for each field. Then run `/second-brain-mapping --type <typename>` to test."*

### Step 5 — First run

Offer to run `/second-brain-mapping --metadata-only --dry-run` to preview what would get extracted. If they agree, run it and report the counts per type.

### Step 6 — Teach the Dataview queries

After first real run, show them 3-5 Dataview queries they can now run on their data. Use the `example_query` field from `schemas.yaml` for each type they enabled. Example:

```
Now that you've extracted book metadata, try this query on any note:

```dataview
TABLE book_author, book_rating_1_5, book_themes
FROM "<your-books-folder>"
WHERE book_rating_1_5 >= 4
SORT book_rating_1_5 DESC
```
```

## Non-negotiables

- No "start small" recommendation. The user gets all capability for their doc types.
- No fabricated types. Only types they've confirmed they actually have, or scaffolds for custom types they explicitly name.
- Every custom extractor starts as a scaffold, not a guess. The user fills in the extraction logic.
- Idempotent: re-running `/setup-vault-types` doesn't break existing configuration — just updates the symlinks.

## Related skills

- `/second-brain-mapping` — runs the full extraction + insight pipeline. Use this AFTER setup.
- `/graphify` — optional Phase 2 of second-brain-mapping. Expensive, opt-in.
