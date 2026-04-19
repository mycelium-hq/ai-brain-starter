# Migration: hooks.json + argument-hints

## What changed

**hooks.json** is now a file in the repo root. It contains the recommended hook templates (UserPromptSubmit session protocol, Stop context save, PreCompact safety net) as a single reference you can pull and re-apply after updates.

Previously, hooks were only embedded in SKILL.md's Phase 5 setup — which meant when hooks improved, existing users had no easy way to update.

**argument-hint** added to skill frontmatter. Slash commands now show inline hints in Claude Code about what arguments they accept.

## How to apply

### Update your hooks (if you ran setup before April 10, 2026)

1. Open `hooks.json` in this repo
2. Compare to your vault's `.claude/settings.local.json` hooks section
3. If they differ, update your settings to match the new hook text

Or just re-run `/setup-brain` — it will detect the existing vault and offer to update your hooks.

### Get argument-hints on existing skills

If you installed skills before April 10, 2026, update the frontmatter of each skill file manually:

**`~/.claude/skills/meeting-todos/SKILL.md`** — add:
```yaml
argument-hint: "[date like 2026-04-09, or meeting title keyword — omit for most recent]"
```

**`~/.claude/skills/insights/SKILL.md`** — add:
```yaml
argument-hint: "[week or month — e.g. 'this week', 'last month', or leave blank for default]"
```

**`~/.claude/skills/graphify/SKILL.md`** — add:
```yaml
argument-hint: "[subfolder path — avoid running on full vault if it has 1000+ files]"
```

Or just reinstall the skill:
```bash
cd ~/.claude/skills/ai-brain-starter && git pull
cp meeting-todos/SKILL.md ~/.claude/skills/meeting-todos/SKILL.md
```
