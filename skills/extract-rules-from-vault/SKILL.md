---
name: extract-rules-from-vault
description: Walk a company's existing artifacts (Slack export, Notion export, GDocs, markdown vault, or any folder of documents) and emit draft hookify rules, draft skills, and a draft CLAUDE.md so a new install does not start empty. Structured-signal-first: parse what is deterministic (channels, users, headings, paths, recurring phrases) before asking the model to infer. The model's job is synthesis on residuals, not classification of everything. Use when onboarding a new company, founder, or team to ai-brain-starter and you want their tribal knowledge encoded as rules from day one.
trigger: /extract-rules-from-vault
argument-hint: "<dump-path> [--out <output-dir>] [--max-files N] [--dry-run]"
---

# /extract-rules-from-vault

Turn an existing company's tribal knowledge into a starter rule layer in one pass. Output is a draft, not a finished install. The founder reviews and accepts before anything ships into a live `CLAUDE.md`.

## Why this exists

Every install of this system today starts from a blank `CLAUDE.md` and an empty `hookify/` directory. The founder writes rules over weeks as Claude makes mistakes the founder corrects. That works, but it leaves the first three weeks unguarded. Companies that already have a Slack history, a Notion workspace, or a Drive of meeting notes have most of the rules already written down somewhere. They just are not in a format the agent can read.

This skill reads what is there, finds the recurring patterns, and writes drafts the founder can accept, edit, or reject. Three weeks of guard-rail accumulation, compressed into one synthesis pass.

## Inputs supported

| Input shape | Detected by | What we extract |
|---|---|---|
| Slack export `.zip` | `users.json` + `channels.json` at root | channel taxonomy, user roles, recurring decision phrases, owner-of-process patterns |
| Notion export `.zip` | nested `.md` with parent-folder `_index.md` shape | page hierarchy, recurring headings, RACI/template patterns |
| GDocs export `.zip` (Takeout) | flat `.docx`/`.html` siblings | doc title patterns, recurring labels, folder semantics |
| Markdown folder (Obsidian, Logseq, plain) | `.md` files with optional frontmatter | frontmatter fields, wikilink density, folder semantics, heading patterns |
| Mixed folder | fall-through | best-effort markdown pass |

If the dump is not one of the above, fall through to the markdown pass on whatever `.md` files exist.

## Outputs

Written to `<output-dir>/` (default: `./extract-rules-output/`):

```
extract-rules-output/
  CLAUDE.md.draft               proposed memory file
  hookify-rules/                one .md per candidate rule
  skills/                       one folder per candidate skill
  signals.json                  raw structured signals (audit trail)
  extraction-report.md          plain-English summary of what was found
  REVIEW.md                     prompts the founder must answer before accepting
```

Nothing in here is auto-applied. The skill prints the path and stops.

## Steps

### Step 0 — Validate the dump

Before any extraction:

```bash
ls "<dump-path>" || (echo "dump path does not exist"; exit 1)
```

If the path is a `.zip`, do NOT auto-unzip into a system temp dir without telling the user where. Ask once: *"This is a zipped export. Unzip into `<output-dir>/_unzipped/` and proceed?"*

Refuse if the dump appears to contain credentials. Run a quick grep for `BEGIN PRIVATE KEY`, `AWS_SECRET_ACCESS_KEY`, `password`, `api_key` in the first 100 files. If any hit, stop and surface the path. The founder confirms it is fine to proceed or scrubs the dump first.

### Step 1 — Run the structured-signal extractor

This is the load-bearing step. Per Build Standards Rule 4a (structured-signal-first), do not call the model on every file. Run the deterministic parser first.

```bash
python3 "${SKILL_DIR}/../../scripts/extract_rules/extract_rules_from_dump.py" \
  --dump "<dump-path>" \
  --out "<output-dir>" \
  ${MAX_FILES:+--max-files $MAX_FILES}
```

The script writes `signals.json` containing:

- `input_type`: slack, notion, gdocs, markdown, mixed
- `entities`: people, channels/folders, recurring titles
- `frequencies`: how often each entity appears
- `decision_phrases`: extracted "we don't do X", "rule is X", "always X", "never X" hits
- `process_signals`: recurring channel-name patterns (`#refunds`, `#incidents`, `#pricing-questions`)
- `template_candidates`: doc heading patterns that recur >= 3 times
- `unresolved`: residual ambiguous items the model should look at

Read `signals.json` after the script finishes. Do NOT proceed to Step 2 until structured-signal coverage is verified.

### Step 2 — Synthesize draft rules from signals

For each high-frequency signal, draft a rule. Use these templates:

**Hookify rule candidate** — when a `decision_phrase` repeats:

> Source phrase: *"never commit secrets to the public repo"* (8 occurrences in #engineering, 3 in #security)
> Drafted rule: block Write/Edit on any file in `**/public/**` containing `BEGIN PRIVATE KEY|AWS_SECRET|api_key=`
> File: `hookify-rules/no-secrets-in-public-paths.md`

**CLAUDE.md authority entry** — when an `owner_of_process` signal repeats:

> Source: 14 of 17 refund decisions in #refunds were resolved by user `@laura` over 6 months
> Drafted entry: *"Refund authority: Laura. Any refund over $500 routes to her before issuing. Refunds under $500 follow the standard credit policy."*

**Skill candidate** — when a `process_signal` shows a recurring multi-step ritual:

> Source: every Friday a thread in #engineering titled *"Week wrap"* contains the same 4 sections (shipped, in-flight, blocked, next-week)
> Drafted skill: `/week-wrap` that prompts for those four sections and files to `📓 Journals/team/`

For each draft, include in the front of the file:

- `confidence: high|medium|low` — based on signal frequency and clarity
- `evidence:` — at least one quoted phrase or path the rule was inferred from
- `review_questions:` — the 1-3 questions the founder must answer to accept

Low-confidence drafts go in `hookify-rules/_low-confidence/` so the high-signal stack stays clean.

### Step 3 — Draft the CLAUDE.md memory

Compose `CLAUDE.md.draft` from these sections, in this order:

1. **# Memory** header
2. **## Who works here** — top 5-10 people by frequency, each with one inferred role line ("Engineering lead based on commit patterns and #engineering activity"). Do NOT invent titles. If unsure, write `[role: REVIEW]`.
3. **## Process authority** — owner-of-process signals, one line each (refunds → Laura, on-call → Marco, pricing exceptions → Pricing Council Slack channel).
4. **## What this company calls things** — recurring proprietary nouns (product names, internal codenames, channel/team names, customer-tier vocabulary). Mine from frequency-ranked unique tokens.
5. **## Rules already in writing** — direct decision phrases from the dump, dated and quoted. These become candidates for hookify next.
6. **## Open loops** — recurring deadline phrases ("by EOQ", "before launch", "post-incident review pending") with their context.
7. **## What this draft does NOT know** — explicit gap list. The founder fills these in. Examples: "compensation philosophy", "promotion criteria", "investor relationships".

Critical: every claim must trace to a signal in `signals.json`. No model-invented facts. If the model wants to assert something that is not in `signals.json`, it goes under "What this draft does NOT know" instead.

### Step 4 — Write the extraction report

`extraction-report.md` is the plain-English version a non-technical founder can read in 5 minutes:

- "We scanned X files in Y format."
- "We found Z people, W channels, V recurring rituals."
- "We drafted N hookify rules, M CLAUDE.md entries, K skill candidates."
- "Our top 3 high-confidence drafts are: ..."
- "Our top 3 review questions for you are: ..."
- "Files we flagged as ambiguous and skipped: ..."

This is what the founder reads first. The drafts are the deliverable; the report is the map.

### Step 5 — Write REVIEW.md

The founder cannot accept all drafts blind. `REVIEW.md` is the gate:

```markdown
# Review before accepting

For each section below, mark Accept / Edit / Reject and (if Edit) the change.

## Authority claims (5)

- [ ] Refunds → Laura. Source: 14/17 refund threads resolved by @laura.
  - Accept / Edit: ____ / Reject

## Hookify rules (12)

- [ ] no-secrets-in-public-paths (high). Source: 11 mentions of "never commit secrets".
  - Accept / Edit / Reject

## Skill candidates (3)

- [ ] /week-wrap (high). Source: 22 weekly wrap threads in #engineering.
  - Accept / Edit / Reject

## Open questions (7)

1. Who decides pricing exceptions over $10K?  (signals are ambiguous between Sales lead and CEO)
   Answer: ____
```

Generate one checkbox per drafted artifact, plus the unresolved questions surfaced in `signals.json`.

### Step 6 — Print the next steps

End the skill output with:

```
Drafts written to <output-dir>.

Next:
  1. Read extraction-report.md (5 min)
  2. Walk through REVIEW.md with the founder (15-30 min)
  3. For each accepted draft, copy it into the live install:
     - hookify-rules/*  →  ~/.claude/hookify/  (or vault `.claude/hookify/`)
     - skills/*         →  ~/.claude/skills/  (or vault `.claude/skills/`)
     - CLAUDE.md.draft  →  merge into your CLAUDE.md
  4. Re-run /diagnose to confirm everything loads.
```

Do not auto-merge. Do not auto-install. Always print the path and stop.

## Edge cases

- **Empty dump.** If `signals.json.entities` has fewer than 5 people OR fewer than 10 distinct files, abort with: *"Dump too small to extract patterns. Need at least 10 documents and 5 distinct authors. Reconnect a longer history."*
- **Non-English dump.** The script handles UTF-8. The synthesis should preserve the original language for proprietary nouns; only translate template scaffolding (e.g., "Memory", "Rules", "Open loops"). Never translate quoted decision phrases.
- **Mixed languages.** If the dump has >20% non-Latin characters, prepend a one-line note in `CLAUDE.md.draft` so a future Claude session knows the team operates bilingually.
- **PII heavy.** If `signals.json.entities` includes more than 50 people, the model is at risk of misattributing rules. Cap the authority section at the top 10 by frequency and put the rest under "Other contributors (review needed)".

## What this skill is NOT

- Not a search index. Glean and Sana already do that.
- Not a knowledge graph. Use `/graphify` after this if you want one.
- Not a one-click migration. The founder reviews every draft.
- Not multi-tenant. This runs locally on a dump on your machine. Cloud export, encrypted upload, multi-team sync are downstream products.

## Provenance

Every drafted rule has a quoted source phrase or file path. Drafts without provenance are a bug. If the model wants to write a rule it cannot ground in `signals.json`, it must instead surface that gap in `REVIEW.md` open questions.

This is the reliability primitive that distinguishes this skill from generic "ask an LLM to summarize the company" approaches. Drift is prevented at extraction time, not detected after the fact.
