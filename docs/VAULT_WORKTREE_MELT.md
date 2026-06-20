# Your vault is for docs. Machinery never lives inside it.

Your brain is a git repository, and the Claude **Desktop** app has a per-session
**worktree** checkbox. On a normal code repo that checkbox is great: it spins up
a throwaway checkout under `.claude/worktrees/<slug>/` so parallel sessions never
collide. On an **Obsidian vault** it is a footgun, because the vault's repo root
*is* the vault root. The worktree is a full second copy of every note, dropped
**inside** the folder Obsidian is watching.

Obsidian then indexes the doubled tree, the single Electron renderer exhausts its
heap, and the app OOM/crashes — a hard `EXC_BREAKPOINT` with the CPU pinned (the
melt measured 2026-06-06). Worse, the Desktop app can silently archive that
worktree mid-session, taking any file that lived **only** in the worktree with it.

The principle is one line:

> **The vault holds documents. Machinery — git internals, worktrees, caches —
> never lives inside the Obsidian-watched tree.**

This is the same invariant as [CLOUD_SYNC.md](CLOUD_SYNC.md) ("the vault may be
synced, the machinery never is"), applied to a different daemon: there the daemon
is iCloud/OneDrive, here it is Obsidian's own file watcher.

---

## The one fix that works: launch the vault PLAIN

There is exactly one reliable remedy, and it is to never create the worktree:

- **Desktop app:** open the vault with the per-session **worktree box
  UNCHECKED**.
- **Terminal:** `cd /path/to/your/vault && claude` — a plain CLI session is
  never a worktree session.

A plain (non-worktree) vault session has nothing to melt. Code isolation still
belongs in a worktree — just on a **code** repo, in a sibling directory
(`~/dev/<repo>-<slug>`), never inside the vault. See
[dev-repo-worktrees](../skills/dev-repo-worktrees) for that pattern.

## What does NOT work (so you don't waste a day on it)

Three "obvious" fixes are all proven non-viable. Do not reach for them, and do
not tell a user they are the fix:

- **"Set the `tengu_worktree_mode` flag."** ❌ The flag does **not** gate Desktop
  worktree creation. The real switch is the per-session checkbox stored in the
  app's local state, not any config-readable flag. Shipping the flag as "this
  prevents the melt" is false guidance.
- **"Symlink `.claude/worktrees/` out of the vault."** ❌ A cloud-sync daemon
  follows the symlink *file* (a few bytes) and stays out — which is why the
  [CLOUD_SYNC.md](CLOUD_SYNC.md) sidecar works for *sync*. But **Obsidian's file
  watcher follows the symlink back IN** and indexes the target anyway, so the
  renderer still melts. Relocation does not solve *this* daemon.
- **"Redirect creation with a WorktreeCreate hook."** ❌ The Desktop app does not
  honor a relocation hint for where it creates the per-session worktree.

Relocation is dead. Prevention (launch plain) is the whole policy.

## How the brain tells you

Two surfaces enforce the principle so a silent melt can't sneak up on you:

| Surface | What it does |
|---|---|
| `hooks/warn-vault-session-in-worktree.py` | **Runtime tripwire.** On SessionStart + each prompt/tool, if this session is running inside a vault worktree it surfaces a LOUD warning on the first turn so you abort and relaunch plain *before* the melt compounds. Three detection channels (payload cwd, transcript marker, and a payload-independent `git rev-parse` ground truth); fires once per session; fail-open; bypass `VAULT_WORKTREE_WARN_BYPASS=1`. |
| `scripts/check-worktree-on-vault.py` (diagnose check 17) | **At-rest scan.** `/diagnose` flags a vault that already has worktree checkouts inside `.claude/worktrees/`, or a `/diagnose` run launched from a worktree cwd. WARN, not FAIL — by the time the directory exists the melt already happened; the remedy is to relaunch plain and let the cleanup hooks reclaim the leftover checkouts. |

Both gate on `.obsidian/` so a **code-repo** worktree never trips them — only a
worktree inside an actual Obsidian vault is the melt class.

## Already melted? Recover, then relaunch plain

1. **Quit Obsidian and close the Desktop session** — stop the renderer from
   re-indexing the doubled tree.
2. **Relaunch the vault PLAIN** (worktree box unchecked, or `cd <vault> &&
   claude`).
3. **Reclaim the leftover checkouts.** The worktree-hygiene hooks remove ended
   scratch worktrees automatically and a session-start cap reclaims any a crash
   left behind (see [CLOUD_SYNC.md](CLOUD_SYNC.md) → "What the brain does"). To
   force it now (snapshot-first, never blind-deletes):
   ```bash
   python3 ~/.claude/skills/ai-brain-starter/scripts/worktree-reclaim.py --dry-run
   python3 ~/.claude/skills/ai-brain-starter/scripts/worktree-reclaim.py
   ```
4. **Confirm green:** `bash ~/.claude/skills/ai-brain-starter/scripts/diagnose.sh
   "<vault>"` — check 17 should read OK.

A vault that melts the editor it lives in isn't a vault you'll keep. Notes stay
inside; machinery stays out; sessions run plain. That's the whole policy.
