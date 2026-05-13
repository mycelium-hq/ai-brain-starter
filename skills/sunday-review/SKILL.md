---
name: sunday-review
description: Weekly meta-review that orchestrates /weekly + /patterns + vault-hygiene + claude-md-drift + decision-retrospective in one flow. Use when the user wants a comprehensive Sunday wrap-up of the week, or says /sunday, /sunday-review, or "let's do the weekly review."
---

# /sunday-review — weekly meta-orchestrator

You are running the Sunday meta-review. This skill doesn't reinvent the existing weekly skills — it orchestrates them in the right sequence, surfaces the cross-cutting signal, and produces ONE clean note instead of N independent reports.

## Order of operations

Run each step in order. After each step, capture the headline finding (1-2 sentences) into the running synthesis. Do NOT dump full reports inline — link to them.

### Step 1 — Pattern recognition (`/weekly`)

Invoke the existing `/weekly` insights skill. It produces the panel-driven journal pattern recognition for the past 7 days. Capture: which floor was dominant, what pattern repeated, what was avoided.

### Step 2 — Instinct Engine (`/patterns`)

Invoke `/patterns`. It scans recent sessions, journals, and decisions for hardening patterns and turns them into concrete captures. Capture: any new patterns ready to codify into a CLAUDE.md rule, concept note, or skill improvement.

### Step 3 — Vault hygiene scan

Run:
```bash
python3 ~/.claude/skills/ai-brain-starter/scripts/vault-hygiene.py --quiet
```

It writes a fresh report to `⚙️ Meta/Vault Hygiene.md`. Capture: how many broken wikilinks, empty notes, stale notes, duplicate concepts.

### Step 4 — CLAUDE.md drift

Run:
```bash
python3 ~/.claude/skills/ai-brain-starter/scripts/check-claude-md-drift.py --quiet
```

It writes a report to `⚙️ Meta/CLAUDE-md drift.md`. Capture: any dormant people, archived projects, broken links, or old codifications that need review.

### Step 4b — Multi-edit semantic drift (if the script exists in this vault)

Run:
```bash
python3 "$VAULT_ROOT/⚙️ Meta/scripts/drift-detection.py"
```

It writes a report to `⚙️ Meta/Drift Audit.md`. Lists vault files edited 5+ times in the last 30 days (configurable via `--days`, `--min-edits`, `--top`, `--include`). Codified-rule files at the top are highest-leverage drift candidates. Capture: which rule file shows highest churn, and whether any of the diffs softened a guard or shifted a number without a Decisions/ entry. Skip silently if the script is missing (vault hasn't installed it yet). Inspired by Microsoft DELEGATE-52 (arxiv.org/abs/2604.15597) finding that frontier LLMs corrupt ~25% of professional content over 20 edits.

### Step 4c — Cross-document rule conflicts (if the script exists in this vault)

Run:
```bash
python3 "$VAULT_ROOT/⚙️ Meta/scripts/check-rule-conflicts.py" --scan-all
```

It writes a report to `⚙️ Meta/Rule Conflicts.md`. Engram-inspired (github.com/Gentleman-Programming/engram) keyword-anchor detector — catches `always X` vs `never X` contradictions across the rules corpus. Add `--semantic` if `ANTHROPIC_API_KEY` is set for vocabulary-different contradiction detection via claude-haiku. Capture: any candidate conflicts at confidence ≥0.5 that need reconciliation. Pair signal with drift detection: drift = single-document shift over time; conflicts = cross-document clash at write time. Skip silently if the script is missing.

### Step 4c.5 — Storage tier audit (if the script exists in this vault)

Run:
```bash
python3 "$VAULT_ROOT/⚙️ Meta/scripts/storage-tier-audit.py"
```

Walks every vault subdirectory, reads its `.tier` declaration (GIT / DB / OS), flags directories missing the declaration or holding GIT-tier files >1MB. Output uses Compiled-Truth + Timeline format at `⚙️ Meta/Storage Tier Audit.md`. Pattern source: garrytan/gbrain (cherry-picked). Capture: how many directories missing tier declarations, any oversized GIT-tier files. Add `.tier` files to the highest-traffic missing directories before next week. Skip silently if the script is missing.

### Step 4c.6 — Zero-LLM typed-relationship refresh (if the script exists in this vault)

Run:
```bash
python3 "$VAULT_ROOT/⚙️ Meta/scripts/wire_typed_relationships.py" \
  --output "$VAULT_ROOT/⚙️ Meta/typed-edges.jsonl"
```

Re-extracts typed edges (frontmatter + wikilinks) across the full vault using regex + entity-type rules. Zero LLM calls. Pattern source: garrytan/gbrain (cherry-picked). The output JSONL feeds `/graphify` Part A.5 so the next graphify run skips the structural extraction LLM cost. Capture: total edges by type (works_at / journaled_about / attended / etc.), runtime in ms, any extraction failures logged to stderr. Skip silently if the script is missing.

### Step 4c.7 — Public repo standards audit (if the script exists in this vault)

Run:
```bash
python3 "$VAULT_ROOT/⚙️ Meta/scripts/audit-public-repo-standards.py"
```

Audits every public non-archived non-fork repo under your GitHub org for baseline standards: LICENSE, README, real CI workflow (Dependabot auto-merge alone does not count), last-push freshness (>60d = stale). Classifies repo type (`code-python`, `code-node`, `code-go`, `code-rust`, `skill`, `docs`, `meta`) so CI requirements only apply to actual code repos. Output uses Compiled-Truth + Timeline format at `⚙️ Meta/Public Repo Standards Audit.md`. Capture: any repos with gaps, especially `missing LICENSE` (MIT add via `gh api -X PUT contents/LICENSE`) or `no CI workflow` (extend the harden script's Layer 6 to handle the missing case). Skip silently if the script is missing.

### Step 4d — Passive captures triage (if the script exists in this vault)

Run:
```bash
SINCE=$(date -v-7d +%Y-%m-%d 2>/dev/null || date -d "7 days ago" +%Y-%m-%d)
python3 "$VAULT_ROOT/⚙️ Meta/scripts/passive-capture.py" --scan-since "$SINCE"
python3 "$VAULT_ROOT/⚙️ Meta/scripts/passive-capture.py" --triage
```

Engram-inspired (`mem_capture_passive`) — scans the past week's session transcripts for utterances pattern-matched as rules, decisions, or lessons that were NOT explicitly filed via `/journal` or `/decision`. Writes triageable stubs to `⚙️ Meta/Passive Captures/{date}-{slug}.md`. Idempotent via state file. Capture: how many pending captures, broken down by type (rule/decision/lesson). Adopt the load-bearing ones into CLAUDE.md or rules/ files; reject and archive the rest. Skip silently if the script is missing.

### Step 4f — Closed-loop week report (if the script exists in this vault)

Run:
```bash
python3 ~/.claude/skills/ai-brain-starter/scripts/closed-loop-week-report.py \
  --vault-root "$VAULT_ROOT" --days 7
```

Reports the previous week's automatic activity in the episodic→procedural memory loop: how many promotion candidates landed in `Meta/Promotion-Candidates/` awaiting human ratification, how many got auto-promoted into `Meta/Workflows/` / `Meta/Exceptions/` / `Meta/Facts/`, how many rules were demoted to `status: superseded`, and the current resolver conflict count. Inline the script's output into the synthesis under "Closed-loop activity." If candidates are pending, the user's "One thing to do this week" should be reviewing them. The closed-loop runs hourly (promote) and weekly (demote/conflicts), but the human ratification gate only fires once a week, here. Skip silently if the script is missing.

### Step 5 — Decision retrospective

Run:
```bash
python3 ~/.claude/skills/ai-brain-starter/scripts/decision-retrospective.py --apply-prompt
```

This surfaces decisions older than 90 days with empty Outcome and appends review-ready prompts to `⚙️ Meta/Decision Retrospective.md`. Capture: how many stale decisions need their Outcome filled in.

### Step 6 — Skill usage curatorial pass (if telemetry enabled)

Run:
```bash
python3 ~/.claude/skills/ai-brain-starter/scripts/skill-usage-report.py
python3 ~/.claude/skills/ai-brain-starter/scripts/curate-skills-surface.py --top 5 --days 7
```

Capture: the 3 most-used skills this week + any skills that haven't been used in 30+ days (dormant — candidates for pruning or re-promoting).

### Step 7 — Synthesize into one note

Write a single markdown note to `📓 Journals/Reviews/Sunday Review {YYYY-MM-DD}.md` with this structure:

```markdown
---
creationDate: {ISO timestamp}
type: review
category: sunday-meta
week_of: {YYYY-MM-DD}
---

# Sunday Review — {YYYY-MM-DD}

## Highlights this week
[1-2 sentences from /weekly + /patterns: what was the dominant emotional pattern, what shipped, what stalled]

## What's hardening (from /patterns)
[any new patterns that appeared 3+ times → ready to codify]

## Vault state
- Hygiene: [link to Meta/Vault Hygiene.md] · {broken wikilinks count}, {empty notes count}, {stale notes count}
- CLAUDE.md drift: [link to Meta/CLAUDE-md drift.md] · {N signals flagged}
- Stale decisions: [link to Meta/Decision Retrospective.md] · {N candidates for outcome backfill}

## Skill usage
- Top this week: {skill 1}, {skill 2}, {skill 3}
- Dormant: {names of skills not used in 30 days}

## One thing to do this week
[Pick the highest-leverage action from the captures above. Just one.]
```

### Step 8 — Surface to the user

Reply with a 2-3 sentence summary. Link to the Sunday Review note. Name the one thing to do this week. End there. Do NOT inline the whole review.

## Why this exists

Five Sunday-relevant skills exist already (`/weekly`, `/patterns`, `vault-hygiene`, `claude-md-drift`, `decision-retrospective`). Running them sequentially by hand is friction. Running them via this orchestrator produces one synthesized output that respects the user's attention budget.

The Matuschak panel critique was that more skills don't deepen thinking unless they compound. This is the compounding layer: it forces the existing tools to interlock once a week.

## When NOT to use this

- During the week (these are weekly-cadence checks; daily use is overkill).
- When the user explicitly only wants `/weekly` (the journal pattern read), not the full meta-review.
- When the user says they want to skip the system and just journal — respect that.

## Configuration

In CLAUDE.md frontmatter, you can disable specific steps:

```yaml
sundayReview:
  skipHygiene: false
  skipDrift: false
  skipRetro: false
  skipTelemetry: true   # if telemetry not opted-in
```

If a step's underlying script is missing, skip silently and note it in the synthesis under "Pending steps."
