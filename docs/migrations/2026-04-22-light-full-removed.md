# Migration: light/full tier removed, everyone gets the full second brain

## What changed

The setup version question ("do you want the light or full setup?") has been removed from Phase 1. Every new install unconditionally gets:

- The advisory panel (named voices in journal entries + insights)
- Knowledge graph context routing (graph-context-hook.sh fires on every prompt)
- Panel-voice routing (panel-trigger-hook fires on every prompt)
- Monthly insight reports with pattern analysis
- The Instinct Engine (`/patterns`)
- The full 12-category version of Rule 19 (corporate event suggestion)

The `PLAN_TIER` variable is no longer collected, stored, or referenced anywhere in the install flow.

## Who this affects

**New installs:** nothing to do. They just get the full version.

**Existing installs that ran setup BEFORE 2026-04-22:** your CLAUDE.md, hooks, and skills already reflect whichever tier you picked. They keep working unchanged. The only thing to clean up is stale `PLAN_TIER` references in your CLAUDE.md or in your local copies of the rule templates — those references are now meaningless markers that no code reads, but they take up space and confuse future maintainers.

## How to apply (existing vaults)

Run these checks. If anything matches, clean it up.

### 1. Search your CLAUDE.md for PLAN_TIER references

```bash
grep -n "PLAN_TIER" "$VAULT/CLAUDE.md" 2>/dev/null
```

If anything matches, open the file and delete those lines. They were notes about which tier you chose during setup. They no longer affect behavior.

### 2. Check the obsidian rules file for the old Rule 19 split

```bash
grep -n "PLAN_TIER" "$VAULT/⚙️ Meta/rules/obsidian.md" 2>/dev/null
```

If the rule still has `[PLAN_TIER == "light" version]` and `[PLAN_TIER == "full" version]` blocks, replace them with the single 12-category version. The canonical source is `templates/generated/obsidian-rules-template.md` Rule 19 in the latest repo.

### 3. If you originally picked "light" and want to upgrade to the full feature set

Your install is missing the graph-context-hook and panel-trigger-hook (Phase 5), the advisory panel skill (Phase 10b), and the full insights skill (Phase 18 sections 3-5 plus the `/monthly` command).

Easiest path: re-run `/setup-brain` and tell it "add the missing full-tier features." It will:

1. Read your existing CLAUDE.md to confirm your context.
2. Install the two hooks (`scripts/graph-context-hook.sh`, panel-trigger-hook) per Phase 5.
3. Generate the full advisory panel skill per Phase 10b (asks you to pick 5-7 voices first if you don't have a panel roster).
4. Replace your light insights skill with the full version per Phase 18.
5. Add a `/monthly` cron job alongside your existing weekly one.

If you originally picked "full," you have nothing to add — you already have everything.

### 4. If you originally picked "full" and have a tier marker somewhere

Run a final sweep:

```bash
grep -rn "PLAN_TIER\|plan_tier\|light mode\|tier-gated\|Tier Gate" \
  "$VAULT/CLAUDE.md" \
  "$VAULT/⚙️ Meta/rules/" 2>/dev/null
```

Delete any stale markers you find. They're cosmetic now.

## Why

The light tier was a defensive posture from when the daily-budget concern was uncertain. Real usage and the workshop on 2026-04-21 showed:

- The full version is what people came for.
- Most light-mode users never figured out what they were missing, so they couldn't make an informed choice to upgrade later.
- The choice itself added friction at the moment of highest abandonment risk (right after install starts).
- Every "light skips X" branch in the phase files added maintenance cost.

Removing the question removes the friction and removes the maintenance overhead in one move.

## Compatibility note

If you have any custom skills or scripts that reference `PLAN_TIER`, they will silently no-op (the variable is just `unset`). Search and update them when convenient.
