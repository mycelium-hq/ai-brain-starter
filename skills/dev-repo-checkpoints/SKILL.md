---
name: dev-repo-checkpoints
description: Auto-stash uncommitted work in code repos on every Claude Code Stop/SubagentStop event, so 60+ exchange sessions can't lose work to a branch switch. Stop hook scoped to ~/dev/* repos (vault is covered by its own snapshot script). Recoverable via `git stash list | grep claude-checkpoint`.
trigger: install once via the Python hook + settings.json registration; fires silently every session-end thereafter
source: pattern from carlrannaberg/claudekit MIT (cli/hooks/create-checkpoint.ts); reimplemented clean in Python per license-hygiene
---

# Dev-Repo Session Checkpoints

A Stop/SubagentStop hook that auto-stashes the working tree of any `~/dev/<repo>` you're working in at every Claude Code session end. No manual checkpointing, no git discipline required, no commit pollution. Recovery is one `git stash apply` away.

This closes a real failure mode: a 60+ exchange Claude Code session in a code repo, branch switches mid-flow, uncommitted work disappears. The vault has `auto-snapshot.sh` covering that surface, but code repos don't — until this hook.

## Why this exists

**The failure mode:** Long Claude Code sessions accumulate uncommitted work — half-finished features, exploratory branches, debugging instrumentation. A branch switch or `git reset --hard` (intentional or auto-triggered by another hook) can wipe that working tree silently. Pre-existing branch-switch-safety hooks catch *unauthorized* switches; this hook catches the broader case where work just isn't saved often enough.

**The fix:** every time Claude Code's session ends (Stop event) or a subagent completes (SubagentStop), the hook detects whether the session was working in a `~/dev/<repo>` git repository and, if there are uncommitted changes, stashes them with a `claude-checkpoint:` prefix and a UTC timestamp. The working tree is unchanged — `git stash create` + `git stash store` doesn't modify state.

Old checkpoints rotate out at 20 by default (configurable). Stashes accumulate in `git stash list` where any normal recovery path picks them up.

**Recovery:**

```bash
cd ~/dev/<repo>
git stash list | grep claude-checkpoint
# stash@{0}: On main: claude-checkpoint: 2026-05-23T17:30:00Z (concierge)
# stash@{1}: On main: claude-checkpoint: 2026-05-23T16:15:00Z (concierge)

git stash apply stash@{0}   # restore + KEEP the stash
# or
git stash pop stash@{0}     # restore + drop the stash
```

## Install

1. **Drop the hook script** at `~/.claude/hooks/create-dev-repo-checkpoint.py`. Source ships in this skill at [`hook.py`](hook.py) below. Make it executable: `chmod +x ~/.claude/hooks/create-dev-repo-checkpoint.py`.

2. **Register in `~/.claude/settings.json`** under both the `Stop` and `SubagentStop` event arrays. Slot this entry into any existing `{"hooks": [...]}` group, or create a new one:

   ```json
   {
     "type": "command",
     "command": "/usr/bin/python3 /Users/<you>/.claude/hooks/create-dev-repo-checkpoint.py 2>/dev/null || true"
   }
   ```

   The `2>/dev/null || true` tail keeps a hook crash from blocking session close — checkpointing is a nice-to-have, not a gate.

3. **Confirm it fires** on the next session-end in a code repo. Look for a new `claude-checkpoint:` entry in `git stash list`. If nothing appears, check there were actual uncommitted changes (hook is a no-op on clean trees).

## Configuration

The hook ships with safe defaults; nothing requires configuration. Bypass for one session:

```bash
DEV_CHECKPOINT_BYPASS=1 claude
```

To change the rotation cap or the stash-message prefix, edit the constants at the top of the script:

```python
PREFIX = "claude-checkpoint"   # prefix in stash messages
MAX_CHECKPOINTS = 20           # rotation cap
```

## Scope: why ~/dev/* only

The hook hard-gates on `cwd` being under `~/dev/`. This is intentional:

- The vault (`~/Desktop/<your-vault>/` in this repo's example) has its own snapshot mechanism (`auto-snapshot.sh` on cron + session-close), tuned for ~60K markdown files. Running `git add -A` in a 60K-file repo would race the index lock and produce 100K+ tokens of `git status` output. The hook explicitly checks for the vault path and exits without doing anything.
- Other locations (`~/Documents/`, `~/Downloads/`, system paths) shouldn't have working trees auto-stashed without explicit opt-in.

If you want the hook to cover a different root (e.g. `~/projects/` instead of `~/dev/`), change the `DEV_ROOT` constant at the top of the script. If you want vault coverage, install `auto-snapshot.sh` separately (different shape — file-list-explicit, not `git add -A`).

## What the hook does NOT do

- **Does NOT commit.** Stashing is recoverable but lightweight; commits would pollute history.
- **Does NOT push.** No network calls, no remote interaction.
- **Does NOT scan recursively.** Only the `cwd`'s repo, not nested repos or sibling repos.
- **Does NOT replace branch-switch-safety.** A separate set of hooks (`block-branch-switch-with-untracked-build.py`, `warn-uncommitted-builds-on-stop.py`) catches *unauthorized* switches with rich messaging. This checkpoint hook is the broader safety net that catches everything else.

## Lineage

Pattern source: [carlrannaberg/claudekit](https://github.com/carlrannaberg/claudekit) MIT `cli/hooks/create-checkpoint.ts`. The TypeScript original is for project-local installation; this Python port is for global `~/.claude/hooks/` registration with scope-guards for the vault-vs-dev-repo split and a defense-in-depth check that the cwd is genuinely under `~/dev/`. Reimplemented clean per `⚙️ Meta/rules/license-hygiene.md` (read in browser, take notes, close tab, write fresh in target style).

Credit the upstream when redistributing.
