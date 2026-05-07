---
name: recommended-skill-overrides
description: Starter recipe for the `skillOverrides` setting in `~/.claude/settings.json`. Sharper auto-routing without disabling skills you might still need.
---

# Recommended skill overrides

Claude Code 2.1.129 added a `skillOverrides` setting that lets you control how skills participate in auto-routing. Three modes per skill:

| Mode | What it does |
|---|---|
| `off` | Skill is hidden from the model and from `/`. Use for collections you'll never invoke. |
| `user-invocable-only` | Hidden from the model (no auto-routing) but still callable via `/`. Use for skills you want to invoke manually but don't want eating routing tokens. |
| `name-only` | Skill name is visible to the model but description is collapsed. Use for skills with long descriptions where the name alone is enough for routing. |

This file is a starter recipe based on a few months of running the substrate against active consulting, writing, and operations work. Adapt to your stack.

## How to apply

Open `~/.claude/settings.json` and add a `skillOverrides` block at the top level (between `model` and `statusLine` if those keys exist):

```json
{
  ...,
  "skillOverrides": {
    "bio-research:start": "off",
    "bio-research:scientific-problem-selection": "off",
    "bio-research:instrument-data-to-allotrope": "off",
    "bio-research:nextflow-development": "off",
    "bio-research:scvi-tools": "off",
    "bio-research:single-cell-rna-qc": "off",
    "finance:sox-testing": "off",
    "finance:audit-support": "off",
    "finance:reconciliation": "off"
  },
  ...
}
```

Validate the file parses as JSON:

```bash
python3 -c "import json,os; json.load(open(os.path.expanduser('~/.claude/settings.json')))"
```

Restart any open Claude Code session so it picks up the new settings.

## Why these defaults

### `bio-research:*` (6 skills, all `off`)

The bio-research collection (single-cell RNA QC, nextflow pipelines, scvi-tools, instrument data conversion, scientific problem selection, environment setup) is targeted at biotech labs and life-sciences researchers. If you're running a consulting practice, building a SaaS product, or writing books, none of these will fire usefully. The skill descriptions consume auto-routing tokens that never resolve to a useful invocation.

If you ARE in life sciences, leave these on; the trim is for non-biotech operators.

### `finance:sox-testing` and `finance:audit-support` (`off`)

These skills support SOX 404 internal-control testing and external-audit response for public companies. Private companies, individual operators, and most consultancies don't run SOX 404 testing. If you ever take a board seat at a public company or run an internal-audit function, turn these back on.

### `finance:reconciliation` (`off`)

Reconciles GL balances against subledgers, bank statements, or third-party data. If your accounting is simpler (single-entity QuickBooks, Xero, no GL reconciliations), the skill won't fire usefully.

If you do run GL reconciliations as a finance function, turn this back on.

## What to keep on

The recipe deliberately leaves these on, even when they look like duplicates:

- **`finance:financial-statements`, `variance-analysis`, `journal-entry`, `journal-entry-prep`, `close-management`** — these have plausible occasional use even for non-public-company operators (private-company books, client work that asks for financial framing, simplified close cycles).
- **`product-management:*`** — overlaps with weekly planning and insights skills but is genuinely different framing.
- **`engineering:*`** — system design, architecture, debugging, code review all see real use across consulting and product work.
- **`design:*`, `marketing:*`, `sales:*`, `legal:*`, `customer-support:*`, `data:*`, `anthropic-skills:*`** — all have plausible cross-stack use cases.

## When to revisit

Run `python3 "⚙️ Meta/scripts/skill-usage-report.py"` after a few weeks of usage. It generates `⚙️ Meta/Skill Usage Report.md` with per-skill invocation counts. If a skill that's currently `on` has zero invocations across a quarter, consider switching it to `name-only` (saves description tokens, keeps it functional) or `off` (if you're sure you won't need it).

If a skill currently `off` would have been useful for a recent task, switch it back to `on` (or `user-invocable-only` if you want manual control).

## See also

- Claude Code 2.1.129 release notes (`skillOverrides` addition): https://github.com/anthropics/claude-code/releases
- `⚙️ Meta/skill-usage-log.jsonl` — per-skill invocation log written by the post-tool-use logging hook
- `⚙️ Meta/Skill Usage Report.md` — aggregated report (run via `skill-usage-report.py`)
