# Hook install architecture

Where ai-brain-starter installs its hooks, why, and how to migrate from older installs.

## TL;DR

- **Hooks install at USER level by default** (`~/.claude/settings.json`).
- **Why:** project-level hooks (`<project>/.claude/settings.json`) silently don't fire when Claude Code runs from inside a git worktree (`<project>/.claude/worktrees/<name>/`). User-level hooks fire universally.
- **Closes [#6](https://github.com/adelaidasofia/ai-brain-starter/issues/6).**
- **Idempotent:** re-running the installer detects already-installed hooks via fingerprint and skips them. Custom user hooks are NEVER touched.
- **Reversible:** `--uninstall` removes only ai-brain-starter entries, leaves everything else intact.

## How to install

New install (already runs as part of `bootstrap.sh`):
```bash
python3 ~/.claude/skills/ai-brain-starter/scripts/install-hooks-user-level.py
```

Preview without writing:
```bash
python3 ~/.claude/skills/ai-brain-starter/scripts/install-hooks-user-level.py --dry-run
```

Verify after install (fires each hook with sample input):
```bash
python3 ~/.claude/skills/ai-brain-starter/scripts/install-hooks-user-level.py --verify
```

Uninstall:
```bash
python3 ~/.claude/skills/ai-brain-starter/scripts/install-hooks-user-level.py --uninstall
```

## Migration from project-level installs

If you installed ai-brain-starter before this fix, your hooks live at project level (`<vault>/.claude/settings.json` or `<vault>/.claude/settings.local.json`). They work in the main vault directory but silently fail in worktrees.

### Automatic detection

The `migrate-to-user-level.py` SessionStart hook detects this and prompts you:

> **Heads up: your ai-brain-starter hooks are installed at project level, which means they don't fire when you work inside a git worktree. To migrate to user-level (universal): run `python3 ~/.claude/skills/ai-brain-starter/scripts/install-hooks-user-level.py`. This is additive — your existing hooks stay, and there's a backup. Want me to run it now?**

The prompt fires once per vault; if you decline, set `migrationDeclined: true` in your CLAUDE.md frontmatter to silence it.

### Manual migration

Run the installer directly:
```bash
python3 ~/.claude/skills/ai-brain-starter/scripts/install-hooks-user-level.py
```

This is **additive**: it adds the hooks to user-level WITHOUT removing them from project-level. Both sets coexist; once you've verified user-level works, you can manually clean up the project-level entries by editing `<vault>/.claude/settings.json`.

### Verifying the fix

Run the worktree firing regression test:
```bash
bash ~/.claude/skills/ai-brain-starter/scripts/test-hooks-in-worktree.sh
```

Six checks:
1. Hook fires from main worktree (sanity)
2. Hook fires from inside a `.claude/worktrees/<name>/` worktree
3. Worktree name is correctly derived from the path
4. Installer preserves user's custom hooks
5. Installer adds ai-brain-starter hooks
6. Installer is idempotent (second run produces identical file)

All six should pass.

## Architecture details

### What gets installed

The hooks shipped by ai-brain-starter (per [`hooks.json`](../hooks.json) source-of-truth):

| Event | Hook | Purpose |
|---|---|---|
| `UserPromptSubmit` | `detect-closing-signal.py` | Detects `bye`/`thanks`/`good night`/etc. and pre-resolves session-close cascade context |
| `UserPromptSubmit` | `log-skill-usage.py` | Opt-in `/skill` invocation logging for usage analytics |
| `UserPromptSubmit` | (legacy session-context loader) | Auto-loads `Last Session.md` + `Current Priorities.md` on first prompt |
| `Stop` | `session-end-hook.sh` | Aggregators, retention cleanup, git snapshot, Haiku fallback |
| `PreToolUse:Write\|Edit\|MultiEdit` | `lint-vault-frontmatter.py` | Blocks malformed YAML in vault frontmatter at write boundary |
| `SessionStart` | `first-week-checkin.py` | Day 3 / 7 / 14 stewardship prompts |
| `SessionStart` | `migrate-to-user-level.py` | Detects project-level installs and offers migration |
| `PreCompact` | (inline systemMessage) | Reminds the model to preserve context before compaction |

### Fingerprinting

The installer identifies "ai-brain-starter-owned" hooks by substring fingerprint, listed in `install-hooks-user-level.py` under `ABS_FINGERPRINTS`. Anything matching a fingerprint is replaced/updated/uninstalled by this tool. Anything not matching is left strictly alone.

When new hooks ship, the fingerprint list is extended in the same release — old versions of the installer will still work but won't manage the new hook entries until updated.

### Backup + rollback

Every install run that modifies `~/.claude/settings.json` creates a backup at `~/.claude/settings.json.bak-{timestamp}-abs`. The installer verifies the post-write JSON parses; on parse failure, it automatically rolls back to the backup.

To restore manually:
```bash
mv ~/.claude/settings.json.bak-2026-04-30-093900-abs ~/.claude/settings.json
```

### Why not also install at project level?

Project-level hooks have their place — they're the right scope for project-specific behavior. ai-brain-starter's hooks are global (every Claude Code session benefits regardless of which project you're in), so user-level is the correct scope. Installing at both creates duplicate firings.

If you have a specific reason to keep project-level hooks (e.g. you're testing changes locally), the installer doesn't touch them — they remain whatever you set them to.

## Troubleshooting

### "My hooks still don't fire in worktrees"

Verify with the regression test:
```bash
bash ~/.claude/skills/ai-brain-starter/scripts/test-hooks-in-worktree.sh
```

If tests pass but you still see no hook firing in your real worktree:
- Check `~/.claude/settings.json` actually has the hooks. Run with `--dry-run` to compare.
- Check that no project-level `.claude/settings.json` is overriding (Claude Code merges, with project taking precedence over user-level for the same event/matcher).
- Check the migration hook fired: look for the migration prompt at SessionStart.

### "I want to opt out of one specific hook"

Edit `~/.claude/settings.json` and remove the hook entry. The installer respects manual edits and won't re-add a removed hook unless you run `--uninstall` followed by a fresh install (which would restore everything).

For more granular control, use the per-hook env-var bypasses:
- `VAULT_LINT_BYPASS=1` — disables vault frontmatter linter
- `CLOSING_SIGNAL_DETECTION=off` — disables session-close detector
- `SKILL_USAGE_TELEMETRY=0` — disables skill-usage logger (default off anyway)

### "I want to disable migration prompts"

Add `migrationDeclined: true` to your CLAUDE.md frontmatter. The migration hook will skip silently for that vault.

## Why this matters

Reports of "I said bye and the cascade didn't run" had a quiet root cause: hooks installed at project level don't fire in worktrees, and worktrees are how Claude Code commonly runs feature branches. The session-close cascade ([2026-04-30 changelog entry](CHANGELOG.md)) shipped with the cascade itself fixed at the architecture level, but the *mechanism* that put the hook in front of the model still depended on project-level config.

This drop closes that last gap. Hooks live at user level, fire universally, and there's a verifiable regression test that proves it. New users get user-level installs by default. Existing users get a one-prompt migration path.

This is the second pass through the same problem class — first the cascade, now the hook delivery vehicle. The combined fix is structurally complete: detection (cascade) + delivery (user-level install) + verification (worktree firing test).
