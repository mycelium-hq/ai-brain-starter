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
