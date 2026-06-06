# Keep your brain local-first

Your brain is a living git repository. Claude Code works inside it with
per-session git **worktrees** — fast, throwaway checkouts under
`.claude/worktrees/`. That design is what makes parallel sessions safe. It
also means the directory churns constantly: thousands of files created and
deleted as you work.

**Consumer cloud-sync tools — iCloud Drive, OneDrive, Dropbox, Google Drive,
Box — are built for documents, not for a churning git tree.** Point one at
your brain and it tries to upload every worktree file, every `.git` object,
every search-index cache, in real time. On an active machine that compounds
into hundreds of thousands of files and a sync daemon pinned at full CPU for
hours. It is the single most common way to make a healthy brain feel broken.

So the rule is simple, and it is a design principle, not a workaround:

> **The vault lives on a local disk. The index lives server-side. Neither
> belongs in a consumer cloud-sync folder.**

The footprint signal at session start will warn you if it detects your vault
inside a sync folder. Here is how to fix it.

---

## The fix, in order of preference

### 1. Best: keep the vault outside every sync folder

Put the vault on a normal local path — `~/brain`, `~/vaults/<name>`,
anywhere that is **not** inside a sync root. On macOS that specifically means
**not** `~/Desktop` or `~/Documents` when iCloud "Desktop & Documents
folders" is on (both are synced). On Windows, not inside `OneDrive\`. Anywhere
else under your home directory is fine.

Already living in a sync folder? Move it out and leave a symlink behind so
every tool that points at the old path keeps working:

```bash
# macOS / Linux — example moving a vault off the iCloud-synced Desktop
mv ~/Desktop/MyVault ~/MyVault
ln -s ~/MyVault ~/Desktop/MyVault   # old path still resolves; iCloud syncs only the tiny symlink
```

Then re-open the vault in Obsidian from the new location and confirm your
tools still resolve. Sync daemons follow the *symlink file* (a few bytes),
not the target's contents — so the churn leaves iCloud's scope entirely.

### 2. If you truly cannot move it: exclude the machine-exhaust

If the vault must stay inside a sync folder, exclude the three directories
that actually churn. This stops the storm even if the notes keep syncing.

- **iCloud Drive (macOS):** iCloud has no per-subfolder toggle. Rename the
  exhaust dirs with a `.nosync` suffix and symlink them back, or — simpler and
  what we recommend — move the *whole vault* out per option 1. Excluding
  subfolders under iCloud is fiddly and easy to get wrong; relocation is the
  honest fix.
- **Dropbox:** Selective Sync (Preferences → Sync) → uncheck
  `.claude`, `.git`, `.smart-env`.
- **OneDrive (Windows/Mac):** right-click the folder → "Always keep on this
  device" off is not enough; use OneDrive settings → "Choose folders" to
  exclude `.claude`, `.git`, `.smart-env`.
- **Google Drive / Box:** use the desktop client's selective-sync / ignore
  settings to exclude the same three.

### 3. Always: keep machine-exhaust out of git too

Separate concern, same dirs. `.gitignore` stops you *committing* the exhaust;
it does **not** stop a cloud daemon from *syncing* it (that's option 1/2).
Your vault `.gitignore` should contain at least:

```gitignore
.claude/worktrees/
.smart-env/
.codegraph/
⚙️ Meta/Worktree Snapshots/
⚙️ Meta/logs/
```

---

## What the brain does instead of cloud sync

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
Copy"** of files on this Mac. Reboot. Turn iCloud Drive back **on**, and do
**not** re-enable "Desktop & Documents folders". This discards the corrupt local
DB and re-fetches a clean one from Apple's servers.

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

A brain that melts the machine it runs on isn't a brain you'll keep. Local
disk for the source, server-side for the index, encrypted-and-verified for
the backup. That's the whole policy.
