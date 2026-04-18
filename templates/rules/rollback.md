---
type: rule
purpose: Restore ~/.claude/settings.json and hook scripts to a known-good state when a recent change breaks the session.
trigger: "hooks are broken" / "nothing is firing" / "rollback" / "revert the last change" / "restore settings"
---

# Rollback runbook

When a recent change to hooks, settings, or plugin config breaks the session, follow this order. Cheapest first, nuclear last.

## 0. Diagnose before reverting

1. `cat ~/.claude/settings.json | python3 -m json.tool` — is it valid JSON?
2. `tail -20 ~/.claude/hooks/*.log` — any error entries?
3. `ls ~/.claude/hooks/sync.*.lock 2>/dev/null` — stuck sync lock?
4. If plugin-related: check plugin hooks JSON parses correctly

If settings.json is invalid, Claude Code ignores the entire hooks block silently. Fix JSON first.

## 1. Revert settings.json

Keep dated backups at `~/.claude/settings.json.bak-*`. List newest first:

```bash
ls -t ~/.claude/settings.json.bak-*
cp ~/.claude/settings.json.bak-<newest-known-good> ~/.claude/settings.json
python3 -m json.tool < ~/.claude/settings.json >/dev/null && echo "JSON OK"
```

Name your backups before making risky changes:
```bash
cp ~/.claude/settings.json ~/.claude/settings.json.bak-$(date +%Y%m%d-%H%M%S)-pre-<change>
```

## 2. Revert a hook script

If a specific hook started behaving wrong:

```bash
mv ~/.claude/hooks/<script>.py ~/.claude/hooks/<script>.py.broken
cp ~/.claude/hooks/<script>.py.bak-<date> ~/.claude/hooks/<script>.py
```

Then verify the settings.json hook entry still points to the right path.

## 3. Clear stuck sync lock

If SessionStart/SessionEnd hangs on sync:

```bash
rm -rf ~/.claude/hooks/sync.*.lock
tail -5 ~/.claude/hooks/sync-*.log
```

## 4. Disable all custom hooks (nuclear)

Rename `~/.claude/settings.json` → `settings.json.disabled`. Claude Code falls back to defaults. Good for isolating "is the problem in my hooks or in Claude Code itself?"

## 5. Plugin sandbox

Disable a plugin via `~/.claude/settings.json` `enabledPlugins` block — set to `false` instead of `true`. Kills that plugin's hooks only, leaves yours.

## 6. Claude Code update rollback

If a Claude Code version update broke something, the binary handles its own downgrade:

```bash
claude --version
# Check the changelog: https://github.com/anthropics/claude-code/releases
```

For version-specific breakage, pin with `CLAUDE_CODE_VERSION=` env var or reinstall an older tag.

## After any rollback

1. Start a new session and verify hooks fire.
2. Document the failure mode — what broke, what fixed it.
3. If the root cause is a Claude Code bug, log it against `anthropics/claude-code` issues after grepping for duplicates.

## Never

- Never `rm -rf ~/.claude/` as a first move. State is recoverable; plugins re-download.
- Never edit settings.json with a hook still holding a lock — race condition.
- Never skip Step 0 diagnosis. Rolling back a working change wastes time.
