---
type: config
skill: rise
created: 2026-05-13
last_updated: 2026-05-13
# Settings for /rise (morning routine skill).
# Default values are privacy-preserving and gender-neutral.
# Edit this file to customize. The skill reads it on every run.
settings:
  # Cycle phase scaling for body movement.
  # Turn on if you have a menstrual cycle and want movement scaled to phase.
  # Turn off if you don't or prefer not to track. Movement will scale on HRV + sleep + feeling only.
  cycle_phase_aware: off
  # Morning anchor practices — the skill asks "have you done these yet?" at step 1.
  # If neither is done, it pauses and waits before continuing.
  # Add or remove practices freely. Empty list = skip the anchor check entirely.
  morning_anchors:
    - meditation
  # To-do file paths (vault-relative). The skill reads each, parses scoring fields,
  # ranks across all files, recommends top 3 priorities for today.
  # Leave empty to skip priorities recommendation entirely.
  todo_files: []
  # Scoring formula weights for priority ranking.
  # Formula: score = impact*w_impact + urgency*w_urgency + (4-effort)*w_effort + commit*w_commit
  # impact: 1-5, urgency: 1-5, effort: S=1/M=2/L=3, commit: Y=1/N=0
  scoring:
    w_impact: 0.40
    w_urgency: 0.30
    w_effort: 0.15
    w_commit: 0.75
  # Calendar pull (Google Workspace MCP required). Surfaces today's events at Step 8.
  calendar: off
  calendar_accounts: []         # leave empty to pull primary; or list account emails to union
  # Health-mcp pull. If on, the skill pulls HRV + sleep + (optionally) cycle phase before recommending movement.
  health_mcp: off
  # Entry save path (vault-relative). Where /rise saves the morning entry.
  # Pattern: <save_path>/<Month YYYY>/YYYY-MM-DD Rise.md
  save_path: "Journals"
---

# /rise Config

This file controls how `/rise` runs every morning. Edit it to match your setup. The skill reads it on every invocation — you stay in control.

## What /rise does

`/rise` is the morning counterpart to `/journal`. Where `/journal` reflects on the day at night, `/rise` declares the day at sunrise: how you're feeling, today's body movement, top priorities, and a single intention. It pairs with `/journal` at night for accountability — the evening journal reads the morning `/rise` entry and asks whether the priorities landed and the intention held.

## Cycle phase scaling

If you have a menstrual cycle and want body movement scaled to phase, turn `cycle_phase_aware: on`. The skill pulls cycle phase from health-mcp (when connected) and adjusts the prescribed flow:

- **Follicular / ovulation:** full mobility + activation
- **Luteal:** full mobility + activation (skip activation if HRV is low)
- **Menstrual:** mobility only, no activation

If you don't have a cycle, leave it off. The skill scales on HRV + sleep + your feeling-check answer instead. The skill never asks you "what phase are you in" — that's a data pull, not an interrogation.

## Morning anchors

Practices the skill asks about at step 1. Default: meditation only. Common anchors:

- `meditation` — sitting practice, breathwork, or anything you call "meditation"
- `red_light` — red-light or near-infrared therapy
- `cold_shower` or `cold_plunge`
- `journal` — if you do morning pages or any pre-`/rise` writing
- `prayer`
- `sunlight` — morning sun exposure
- `walk` — pre-routine walk

The skill asks "have you done your [anchor 1] and [anchor 2] yet?" If you say no, it pauses and waits for you to do them. If you say skip-today, it logs the skip and continues. Empty list = skip the anchor check entirely.

## To-do file paths

If you want priorities recommended from your task files, list the vault-relative paths here. Example:

```yaml
todo_files:
  - "Tasks/Today.md"
  - "Tasks/This Week.md"
  - "Work/Projects/Active.md"
```

The skill reads each file, parses inline `[impact:: N] [urgency:: N] [effort:: S|M|L] [commit:: Y|N]` fields, applies the scoring formula, ranks across all files, surfaces top 5, recommends top 3. You confirm 1-3 or swap.

Leave empty to skip priorities recommendation entirely. The skill will ask you directly: "What are your top 1-3 priorities today?"

**Tag format:** if your files don't use the `[field:: value]` Dataview inline tag pattern, the skill recommends by file modification date + age instead, and flags everything `[needs-context]`. To get the ranked recommendation, add the inline tags to your tasks:

```markdown
- [ ] Ship the redesigned hero section [impact:: 4] [urgency:: 5] [effort:: M] [commit:: Y]
```

## Calendar pull

If `calendar: on` and the Google Workspace MCP is connected, the skill surfaces today's events at Step 8. Set `calendar_accounts: []` to pull primary, or list emails to pull across multiple accounts (each result unioned and deduped by event ID).

## Health-mcp pull

If `health_mcp: on` and the health-mcp connector is configured, the skill pulls HRV, sleep, and optionally cycle phase before recommending movement. Without it, the skill recommends based on your feeling-check answer alone.

## Where /rise saves the entry

`save_path: "Journals"` writes to `<vault>/Journals/<Month YYYY>/<YYYY-MM-DD> Rise.md`. Match the path to where your `/journal` evening entries live so the pairing (morning declares → evening reflects) reads naturally.

## Common configs

**"Just consciousness + body, no operations":**

```yaml
settings:
  cycle_phase_aware: on
  morning_anchors: [meditation]
  todo_files: []
  calendar: off
  health_mcp: on
```

**"Full operations + cycle scaling":**

```yaml
settings:
  cycle_phase_aware: on
  morning_anchors: [meditation, red_light]
  todo_files:
    - "Tasks/Today.md"
    - "Tasks/This Week.md"
  calendar: on
  health_mcp: on
```

**"Bare-bones, no cycle, no anchors":**

```yaml
settings:
  cycle_phase_aware: off
  morning_anchors: []
  todo_files: ["Tasks/Today.md"]
  calendar: off
  health_mcp: off
```

## How the skill installs this file

If `Meta/rise-config.md` (or `⚙️ Meta/rise-config.md` for emoji-prefixed vaults) doesn't exist when `/rise` runs, the skill copies this template into your vault and asks you the essential questions once (do you want cycle scaling, what are your morning anchors, where are your to-do files). Your answers get written into the file. The skill never re-prompts after that — you stay in control by editing the file directly.
