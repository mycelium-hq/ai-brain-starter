---
name: dev-repo-worktrees
description: Per-session git worktree pattern for ~/dev/<repo> code repos. Prevents the CONCURRENT-SESSION-HEAD-DRIFT bug class where two Claude Code sessions writing to the same physical checkout collide on the single .git/HEAD pointer + index + working tree. Ships a wrapper script + hookify warn rule + the rule prose. Complements dev-repo-checkpoints (recovery) by preventing the failure at the structural layer (isolation).
trigger: install the wrapper at ~/.local/bin/claude-dev-worktree + the hookify rule at the vault's .claude/. Call `claude-dev-worktree start <repo> <slug>` at session start when the session is going to write code to ~/dev/<repo>/.
source: codified after the second concurrent-Claude-session HEAD-drift collision in 16 hours
---

# Dev-Repo Worktrees

Per-session git worktree pattern for `~/dev/<repo>/` code repos that prevents concurrent Claude Code sessions from colliding on the shared `.git/HEAD`.

## Why this exists

**The failure mode (CONCURRENT-SESSION-HEAD-DRIFT):** Two Claude Code sessions both editing code in `~/dev/<repo>/` share one physical checkout, which means one `.git/HEAD` + one index + one working tree. When session A checks out their feature branch, session B's next `git commit` lands on session A's branch by accident. Recovery requires branch-label manipulation + `git stash` dances + branch-switch-safety hook overrides. Observed multiple times in long-running multi-session workflows.

**The cause:** Bash `cd` is per-command, not per-session. Every invocation re-cds; HEAD-state from prior commands is whatever the last command left it. Bash sessions cannot share filesystem state with other Bash sessions — but git operations on the same checkout absolutely DO share state, and the model can't observe that.

**The fix:** every Claude Code session that writes code in `~/dev/<repo>/` works in its own per-session git worktree at `~/dev/<repo>-<slug>/`. Each worktree has its own HEAD + own index + own working tree, while sharing the underlying object store. Zero collision possible.

```
~/dev/<repo>/                       NEVER write here in a session
~/dev/<repo>-<slug>/                YES — session checkout, isolated HEAD
```

The main checkout stays as the maintenance + reference path — fetches + integration view. Session writes go through the worktree.

## When the pattern DOES apply

- Multi-step feature work in `~/dev/<repo>/`
- Anything that involves `git commit` or `git push` from the session
- Any task that runs builds / tests / code modifications

## When the pattern does NOT apply

- Single-file edits (typo fix, README tweak) — overhead exceeds value
- Read-only audits (`cat`, `grep`, `git log`, `git diff`) — no HEAD writes
- Vault git (markdown notes / second-brain) — vault has its own worktree mechanism with different semantics (see `superpowers:using-git-worktrees`)

## Install

### 1. Drop the wrapper script

Copy [`claude-dev-worktree`](claude-dev-worktree) to `~/.local/bin/claude-dev-worktree`:

```bash
cp skills/dev-repo-worktrees/claude-dev-worktree ~/.local/bin/claude-dev-worktree
chmod +x ~/.local/bin/claude-dev-worktree
```

Verify on PATH: `which claude-dev-worktree`.

### 2. (Optional) Drop the hookify warn rule

Copy [`hookify.warn-dev-repo-shared-checkout.local.md`](hookify.warn-dev-repo-shared-checkout.local.md) to your vault's `.claude/` directory and customize the `(your-repo-1|your-repo-2|...)` capture group in the pattern to match your actual high-concurrency repos.

The hookify rule fires on `cd ~/dev/<known-shared-repo>` (no worktree suffix) and surfaces the pattern. Action is `warn`, not `block` — false-positive rate is acceptable because every miss-as-warn-only is just a reminder, never a block of legitimate work.

### 3. Reference the rule from your CLAUDE.md

Add to your CLAUDE.md `# Rules` section:

```markdown
- **External-repo worktrees** (`<your-rules-dir>/external-repo-worktrees.md`):
  every Claude session that writes code in `~/dev/<repo>/` MUST work in a
  per-session git worktree at `~/dev/<repo>-<slug>/`, NEVER in the main
  checkout. Wrapper script `~/.local/bin/claude-dev-worktree start <repo>
  <slug>` automates creation; `cleanup <repo> <slug>` removes after PR
  merges. Bypass: `DEV_WORKTREE_BYPASS=1` for read-only audit work.
```

The rule file itself is documented in this SKILL.md — the wrapper + hookify are the enforcement layers; the CLAUDE.md entry is the discoverability layer.

## Usage

At session start, BEFORE first edit on a `~/dev/<repo>` issue:

```bash
claude-dev-worktree start <repo> <slug>      # creates ~/dev/<repo>-<slug>/
cd ~/dev/<repo>-<slug>
# all work happens here — isolated HEAD, no collision
```

At session close (after PR merges):

```bash
claude-dev-worktree cleanup <repo> <slug>    # removes worktree + local branch
```

Inspect every active worktree across all repos under `~/dev/`:

```bash
claude-dev-worktree list
```

## How it compares to other patterns

| Pattern | Mechanism | When it fires |
|---|---|---|
| **This skill** (`dev-repo-worktrees`) | Per-session `git worktree add` | Session start, BEFORE first write |
| `dev-repo-checkpoints` skill | Auto-stash on Stop event | Session end, AFTER work would have been lost |
| `branch-switch-safety` rule | PreToolUse block on destructive ops with untracked work | When a destructive op is attempted |

The three patterns are complementary:
- `dev-repo-worktrees` PREVENTS the collision by structural isolation
- `dev-repo-checkpoints` RECOVERS lost work via auto-stash
- `branch-switch-safety` BLOCKS the destructive op when work would be lost

A robust setup runs all three. Worktree-per-session is the cheapest insurance — disk cost is ~500MB per worktree (typical Node + Cargo project), trivially less than the cost of one corruption incident.

## Disk cost

Each worktree is a full checkout. With 3 concurrent sessions on a typical fullstack repo (~500MB working tree with build-tool caches like `target/`, `.next/`, `.gradle/`, etc.), worktrees add ~1.5GB. Some package managers share their store across worktrees automatically (e.g. pnpm via `node_modules/.pnpm`); language build caches (cargo `target/`, gradle `.gradle/`) are typically per-worktree and cannot easily share without symlink tricks.

Not a legitimate blocker. Disk is cheap; mid-build corruption is not.

## Bug class

`CONCURRENT-SESSION-HEAD-DRIFT`. Parent class: `ARTIFACT-WITHOUT-ISOLATION-WIRING` — siblings include `ARTIFACT-WITHOUT-UMBRELLA-WIRING` (skill installs without routing wires) and `ARTIFACT-WITHOUT-DEPENDENCY-WIRING` (Linear issues created without blocker relations). All share the same shape: a thing gets created without its required structural connection wired in the same beat.

## Bypass

`DEV_WORKTREE_BYPASS=1` for legitimate single-session work in the main checkout — rare, typically only when fetching + reading without writes.

## Credit

Originally codified in a personal Claude vault as `external-repo-worktrees.md` after the second concurrent-session HEAD-drift collision in 16 hours. The pattern is universal — published to the public substrate so anyone running multi-session Claude Code workflows can install it without rediscovering the failure mode.
