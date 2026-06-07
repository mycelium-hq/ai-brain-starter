# Your vault can live in iCloud. Its machinery can't.

Your brain is a living git repository. Claude Code works inside it with
per-session git **worktrees** — fast, throwaway checkouts under
`.claude/worktrees/`. That design is what makes parallel sessions safe. It
also means the directory churns constantly: thousands of files created and
deleted as you work, a `.git` that a single `git gc` rewrites wholesale, and
search-index caches that rebuild on the fly.

Point a consumer cloud-sync daemon — iCloud Drive, OneDrive, Dropbox, Google
Drive, Box — at that churn and it tries to upload every worktree file, every
`.git` object, every cache, in real time. On an active machine that compounds
into hundreds of thousands of file events and a sync daemon pinned at full CPU
for hours. It is the single most common way to make a healthy brain feel broken.

The storm hides one fact: your *notes* are not the problem. Markdown is tiny
and barely changes. The freeze comes entirely from the **machinery** — `.git`,
worktrees, caches — living inside the synced tree. So the rule is not "never
sync your brain." The rule is:

> **The vault may be synced. The machinery never is.**

That gives you two supported shapes, both first-class. Pick by whether you want
your notes on your phone. The footprint signal at session start will warn you if
it sees machinery inside a sync folder; here is how to set up either shape.

---

## Two supported shapes

### Shape A — vault fully local (simplest)

Put the vault on a normal local path — `~/brain`, `~/vaults/<name>`, anywhere
**not** inside a sync root. On macOS that means **not** `~/Desktop` or
`~/Documents` when iCloud "Desktop & Documents" is on (both are synced); on
Windows, not inside `OneDrive\`. The index lives server-side; backups are a
deliberate off-machine choice (below). Nothing to configure — this is the
default.

Already inside a sync folder and you don't need phone access? Move it out onto a
local disk with the helper — **not** a raw `mv`. A bare move relocates the files
but silently orphans your **Claude Code session history**: Claude keys
per-project state on the vault's absolute path, so moving the vault makes every
prior transcript read *"Session history unavailable"* and leaves the agent-memory
symlink dangling. The helper does the move, leaves a symlink at the old path, AND
re-homes that Claude state (copying it, so the old location stays a backup):

```bash
# preview first (changes nothing)
bash scripts/relocate-vault.sh ~/Desktop/MyVault ~/MyVault --dry-run
# do it (quit Obsidian + close Claude sessions first; --force overrides the soft gates)
bash scripts/relocate-vault.sh ~/Desktop/MyVault ~/MyVault
```

Already moved it with a plain `mv` and lost your session picker? Re-home just the
Claude Code state, no second move:

```bash
bash scripts/relocate-vault.sh --migrate-claude-state ~/Desktop/MyVault ~/MyVault
```

Sync daemons follow the *symlink file* (a few bytes), not the target's
contents — so the churn leaves the sync scope entirely.

> **One failure, two shapes.** Whether a bare `.git/` sits inside a sync mirror
> or a whole git-backed vault sits inside a sync root, the cause is identical:
> high-churn git machinery + a real-time sync daemon. Shape A (above) moves the
> vault out; Shape B (below) keeps the vault synced and moves only the machinery.
> Either removes the churn from the sync scope — that is the whole policy.

### Shape B — vault synced, machinery in a local sidecar (notes on every device)

This is the mode that lets you **keep your notes in iCloud and edit them on your
iPhone**, two-way, without the storm. It relocates every churning machinery dir
OUT of the synced tree into a local sidecar and leaves only tiny static pointers
behind:

- `.git` → a real git directory outside the tree, via
  `git init --separate-git-dir`, leaving a one-line `.git` **pointer file** in
  the vault (static, safe to sync).
- `.claude/worktrees/` and the caches (`.smart-env`, `.codegraph`, graph output,
  session logs, snapshots) → relocated to the sidecar with a symlink back. The
  sync daemon follows the symlink (a few bytes), never the target's churn.

One command sets it up. Run it with **all Claude sessions closed and no scratch
worktrees live** — separating the git directory orphans live worktrees, so the
script refuses unless the window is clean (`--force` to override):

```bash
# preview first (changes nothing)
bash scripts/relocate-machinery-sidecar.sh "/path/to/vault" --dry-run
# do it (default sidecar: ~/.brain-sidecar; override with --sidecar or $BRAIN_SIDECAR)
bash scripts/relocate-machinery-sidecar.sh "/path/to/vault"
# fully reversible — restores a normal local repo
bash scripts/relocate-machinery-sidecar.sh "/path/to/vault" --rollback
```

Then turn on iCloud Drive (or Desktop & Documents) for that folder. The docs
sync to every device; the machinery never leaves your Mac. Verify the calm
yourself: run a `git gc` plus a full session and watch Activity Monitor —
`fileproviderd`/`bird` stay idle.

> **Second Mac?** The `.git` pointer syncs as static text but points at *this*
> Mac's sidecar. On another Mac, re-run the helper there to stand up its own
> sidecar. On iPhone there is no git, so the pointer is harmless — you just see
> your notes.

> **`.gitignore` is not enough.** It stops you *committing* the machinery; it
> does **not** stop a cloud daemon from *syncing* it. The bytes must physically
> leave the synced tree (Shape B) or be flagged `.nosync` (the helper's
> `--nosync` mode renames caches to `<name>.nosync`, which iCloud ignores by
> name). Keep the machinery out of git too — your `.gitignore` should contain at
> least:
>
> ```gitignore
> .claude/worktrees/
> .smart-env/
> .codegraph/
> ⚙️ Meta/Worktree Snapshots/
> ⚙️ Meta/logs/
> ```

---

## What the brain does for sync safety

- **Worktree hygiene is automatic.** Each session's worktree is removed when
  the session ends; a session-start cap reclaims any that a crash left behind;
  unsaved work is snapshotted first and committed work is preserved on its
  branch. You never accumulate a pile. (See `docs/HOOKS_INSTALL.md`.)
- **Backups are a deliberate, off-machine choice** — one compressed daily
  snapshot to a destination you pick, with a restore you actually verify — not a
  side effect of a sync daemon that also happens to hold your secrets in
  plaintext. One command sets it up: `bash scripts/vault-backup.sh setup`
  (encrypted with `--encrypt`). (See `docs/BACKUP.md`.)
- **The index is server-side.** For Mycelium runtime users, the searchable
  index lives in the runtime, not in a synced local folder. Your laptop holds
  the source notes on a local disk; the heavy index never touches your
  machine's sync scope.

## The guardrails, concretely

These ship as session hooks (install via `docs/HOOKS_INSTALL.md`). They are
**non-destructive by design**: they reclaim only what is provably
reconstructible, and they *surface* (never auto-delete) anything that needs
judgment.

| When | Hook | What it does |
|---|---|---|
| SessionEnd | `remove-ended-worktree.py` | removes that session's scratch worktree (committed work stays on its branch, unsaved work is snapshotted first) |
| SessionStart | `enforce-worktree-cap.py` | caps scratch worktrees (default 12), reclaiming the oldest idle ones a crash left behind |
| SessionStart | `worktree-footprint-signal.py` | warns early on worktree count, orphan dirs, low free disk, and the dangerous vault-in-a-cloud-sync-folder combo |
| SessionStart | `remediate-runaway-procs.py` | reaps orphaned runaway processes (the `yes`-pileup class), pure waste with zero recoverable output |
| weekly cron | `scripts/worktree-prune.sh` | backstop: safe reclaim of orphan dirs + merged-branch cleanup + snapshot retention |
| on-demand / weekly | `hooks/check-sync-folder-machinery.py` | audits **every** cloud-synced root (iCloud Drive, iCloud Desktop & Documents, OneDrive, Dropbox, Box, Google Drive) for machinery — `.git`, `node_modules`, build dirs, any 5k+-file dir — *anywhere on the machine*, not just the vault. Broader than the per-session `worktree-footprint-signal.py` (which only checks the vault's own location). Advisory, never blocks; `--self-test` proves it fires. |

**The non-destructive contract.** Auto-remediation fixes only reconstructible
things: a scratch worktree directory (recreatable from its branch), an orphaned
runaway process (no output to lose), git's stale worktree refs. It NEVER
auto-deletes the judgment calls (unpushed commits, stashes, or a directory
whose git metadata it cannot reason about); those are *surfaced* for you to
decide. The discriminator for worktree removal is **location**
(`.claude/worktrees/` scratch), not branch name: a deliberate
`~/dev/<repo>-<slug>` sibling worktree is never touched, even when idle and on a
`claude/*` branch.

**Force a reclaim now** (snapshot-first; classifies each dir, never
blind-deletes; a dir with genuinely-unsaved work or dangling git metadata is
kept and reported):

```bash
# preview what would be reclaimed
python3 ~/.claude/skills/ai-brain-starter/scripts/worktree-reclaim.py --dry-run
# do it
python3 ~/.claude/skills/ai-brain-starter/scripts/worktree-reclaim.py
```

**Don't write secrets into notes.** A live API key in a note gets committed,
synced, and indexed. The `block-secret-in-note.py` write guard refuses a
Write/Edit that would put a high-confidence credential (AWS / GitHub PAT /
provider keys / database-URL passwords) into a `.md`/`.txt` note. Store it in
the keychain or a gitignored secrets file and reference it by name instead.

## Already melting? Rebuild the sync DB

If a sync daemon is *already* pinned — on macOS, iCloud's `fileproviderd` and
`bird` at 70-130% CPU for hours, a Finder that beachballs, files that won't
download — the damage is usually a **corrupted local sync database**: it
references hundreds of thousands of items that no longer exist and retries them
forever. Removing the churn (above) stops it getting *worse*; it does **not**
drain a backlog that already exists. You have to rebuild the database.

Do it in this order, and **measure before and after each step — don't guess.**
Stop at whichever step drops the CPU.

**0. Confirm the diagnosis** (macOS):

```bash
# how many phantom entries is the File Provider DB retrying?
fileproviderctl dump 2>/dev/null | grep -c itemNotFound
# is fileproviderd actually pegged? (watch several samples, not one)
top -l 4 -s 12 -o cpu -stats command,cpu | grep -E 'fileproviderd|bird'
```

A six-figure `itemNotFound` count plus sustained high CPU is the signature.

**1. Remove the cause first.** Run the machinery audit and move anything it flags
out of every sync folder. A rebuild only stays clean if nothing is still feeding
it:

```bash
python3 ~/.claude/skills/ai-brain-starter/hooks/check-sync-folder-machinery.py
```

**2. Try the in-place repair (non-destructive).** macOS ships a consistency
checker/repairer for the File Provider DB:

```bash
fileproviderctl check  -P -o /tmp/fpck-check.txt    # read-only: see the breakage
fileproviderctl repair -P -o /tmp/fpck-repair.txt   # attempt an in-place reconcile
```

Re-measure. If the `itemNotFound` count and CPU drop, you're done. If `repair`
finishes with `FPCKDomain Code=65` and the counts **don't** move, the domain is
too corrupted for in-place repair — go to step 3.

**3. Rebuild from the server (the supported reset).** System Settings → your
Apple Account → iCloud → **iCloud Drive** → turn it **off**, choosing **"Keep a
Copy"** of files on this Mac. Reboot. Turn iCloud Drive back **on**. Leave
"Desktop & Documents folders" off *unless* you have set up Shape B above (the
machinery sidecar) — once the machinery is out of the synced tree, re-enabling
D&D is safe. This discards the corrupt local DB and re-fetches a clean one from
Apple's servers.

- Expect a CPU spike and a long re-sync afterward — that part is normal; let it
  run (hours, on a large drive).
- **Back up first** (next section). Your local files are kept, but a tested backup
  is the only safe way into an irreversible iCloud operation.

> Heads-up: some users report Calendar/Contacts duplication after toggling iCloud,
> and especially after signing out of the **whole** Apple Account. Toggle **only
> iCloud Drive** — it's the narrower, safer move — and avoid a full account
> sign-out unless step 3 alone doesn't take.

Verify success the way you diagnosed it: the `itemNotFound` count collapses and
`fileproviderd` settles to near-zero at idle.

## Order matters: back up before you move

Relocating the vault out of a sync folder is the right fix, but the vault is
often the one irreplaceable asset, so **stand up an off-machine backup and pull a
real restore from it FIRST, then relocate.** A backup you have never restored is
a hope, not a backup. One command gets you protected immediately —
`bash scripts/vault-backup.sh setup` (add `--encrypt` for a sensitive vault),
then `bash scripts/vault-backup.sh verify` to prove the restore. Full guide,
including the restic option for an offsite tier: `docs/BACKUP.md`.

A brain that melts the machine it runs on isn't a brain you'll keep. Whichever
shape you pick — fully local, or synced with the machinery in a sidecar — the
invariant is the same: notes can sync, machinery never does, the index lives
server-side, and the backup is encrypted-and-verified. That's the whole policy.
