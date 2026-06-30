"""Shared worktree-safety helpers for the worktree-lifecycle hooks.

Why this exists
---------------
Git worktrees under `.claude/worktrees/<slug>/` are throwaway per-session
scratch checkouts. Nothing in stock Claude Code removes them when a session
ends, so on an active machine they accumulate — each one a FULL checkout of
the vault. Left alone they reach hundreds of worktrees / millions of files,
which then melts any cloud-sync daemon (iCloud / OneDrive / Dropbox) pointed
at the vault and burns disk. This module is the safe-cleanup core shared by:

  - remove-ended-worktree.py      (SessionEnd: clean up the just-ended one)
  - enforce-worktree-cap.py       (SessionStart: bound the total, reclaim-then-allow)
  - worktree-footprint-signal.py  (SessionStart: observe before it bloats)

The recoverability guarantee
----------------------------
A worktree directory is safe to delete iff every file in it is recoverable:

  * COMMITTED work       -> preserved by the branch ref (`git worktree remove`
                            keeps the `claude/<slug>` branch; only the working
                            directory is deleted).
  * content already in git -> recoverable from the object DB. Worktrees SHARE
                            the main repo's object store, so `git hash-object`
                            + `git cat-file --batch-check` is a DEFINITIVE test
                            of "is this exact content stored anywhere in git?"
  * genuinely-unsaved    -> content that hashes to a blob NOT in the object DB.
                            We SNAPSHOT these to the main repo before deletion.

`unrecoverable_content()` returns exactly the genuinely-unsaved set. It fails
SAFE: on any git hiccup it returns the whole candidate list (over-preserve),
never the empty set. This is what lets cleanup be aggressive without ever
losing work — verified on a 102-worktree / 1.29M-file backlog where exactly
one un-snapshotted file existed across all worktrees and the test caught it.

Portable: no hardcoded paths; resolves the repo from cwd / CLAUDE_PROJECT_DIR.
Pure stdlib.
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import time
from pathlib import Path

# Canonical snapshot location — MUST match snapshot-pending-work-on-stop.py and
# surface-orphan-worktree-snapshots.py so orphan-surfacing + weekly prune find
# snapshots written here. Falls back to a dot-dir for non-vault repos.
SNAPSHOT_REL = "⚙️ Meta/Worktree Snapshots"
SNAPSHOT_REL_FALLBACK = ".worktree-snapshots"
WORKTREES_SEG = ".claude/worktrees"

# Heavy machine-exhaust dirs: never counted as "work" for idle detection.
EXHAUST = {
    ".git", ".smart-env", ".claude", "node_modules", ".venv", "__pycache__",
    ".codegraph", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".obsidian",
    ".trash", ".DS_Store",
}

GIT_TIMEOUT = 120


def find_main_repo(cwd: Path | None = None) -> Path | None:
    """Resolve the main checkout that owns `.claude/worktrees/`.

    1. CLAUDE_PROJECT_DIR env var (set by Claude Code) if it's a real dir.
       If that value itself sits inside `.../.claude/worktrees/<slug>/`
       (Claude Code commonly sets it to the session cwd, which IS the
       worktree path), collapse it back to the part before so logs and
       snapshots written via this helper never strand on a throwaway
       claude/<slug> branch.
    2. If cwd is inside `.../.claude/worktrees/<slug>/`, the part before
       `.claude/worktrees`.
    3. cwd itself if it contains `.claude/worktrees/`.
    4. Walk up cwd for a parent containing `.claude/worktrees/`.
    Returns None if nothing resolves.
    """
    cwd = (cwd or Path.cwd()).resolve()
    marker = "/" + WORKTREES_SEG + "/"

    env_root = os.environ.get("CLAUDE_PROJECT_DIR")
    if env_root:
        cand = Path(env_root)
        if cand.is_dir():
            cand = cand.resolve()
            s = str(cand)
            if marker in s:
                return Path(s.split(marker, 1)[0]).resolve()
            return cand

    s = str(cwd)
    if marker in s:
        return Path(s.split(marker, 1)[0]).resolve()

    if (cwd / WORKTREES_SEG).is_dir():
        return cwd
    for parent in cwd.parents:
        if (parent / WORKTREES_SEG).is_dir():
            return parent
    return None


def current_worktree(cwd: Path | None = None) -> tuple[Path, str] | None:
    """If cwd is inside `.../.claude/worktrees/<slug>/`, return (path, slug)."""
    cwd = (cwd or Path.cwd()).resolve()
    marker = "/" + WORKTREES_SEG + "/"
    s = str(cwd)
    if marker not in s:
        return None
    head, tail = s.split(marker, 1)
    slug = tail.split("/", 1)[0]
    if not slug:
        return None
    return Path(head + marker + slug), slug


def snapshot_dir_for(main_repo: Path) -> Path:
    """Canonical snapshot root for this repo (vault dir if present, else dot-dir)."""
    vault_meta = main_repo / SNAPSHOT_REL
    if (main_repo / "⚙️ Meta").is_dir() or vault_meta.exists():
        return vault_meta
    return main_repo / SNAPSHOT_REL_FALLBACK


def git(repo: Path, args: list[str], timeout: int = GIT_TIMEOUT) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, timeout=timeout,
    )


def list_worktrees(repo: Path) -> list[Path]:
    """Registered worktree paths (excluding the main checkout)."""
    try:
        out = git(repo, ["worktree", "list", "--porcelain"])
    except (subprocess.TimeoutExpired, OSError):
        return []
    paths = [
        Path(l[len(b"worktree "):].decode("utf-8", "replace"))
        for l in out.stdout.splitlines()
        if l.startswith(b"worktree ")
    ]
    repo_r = repo.resolve()
    return [p for p in paths if p.resolve() != repo_r]


def is_scratch_worktree(wt: Path) -> bool:
    """True if `wt` is a throwaway scratch worktree under `.claude/worktrees/`.

    The cap + reclaim only AUTO-REMOVE scratch worktrees. A deliberate
    `~/dev/<repo>-<slug>` sibling worktree (created by a per-session worktree
    pattern, often on its own feature branch) is NEVER auto-removed even when
    idle and on a `claude/*` branch — its lifecycle belongs to that workflow,
    not to this cap. Location, not branch name, is the safe discriminator.
    """
    marker = "/" + WORKTREES_SEG + "/"
    try:
        return marker in str(wt.resolve())
    except OSError:
        return marker in str(wt)


def is_idle(path: Path, idle_min: int = 60) -> bool:
    """True if no work file under `path` was modified in the last idle_min minutes.

    Prunes heavy hidden dirs for speed and early-exits on the first recent file,
    so active worktrees are detected fast. Uses mtime (not atime), so merely
    reading files does not mark a worktree active.
    """
    cutoff = time.time() - idle_min * 60
    try:
        for root, dirs, files in os.walk(path):
            dirs[:] = [d for d in dirs if d not in EXHAUST]
            for f in files:
                try:
                    if os.path.getmtime(os.path.join(root, f)) > cutoff:
                        return False
                except OSError:
                    continue
    except OSError:
        return True
    return True


def dirty_files(worktree: Path) -> list[Path]:
    """Absolute paths of uncommitted/untracked files in the worktree."""
    try:
        out = subprocess.run(
            ["git", "-C", str(worktree), "status", "--porcelain", "-z"],
            capture_output=True, timeout=60,
        )
    except (subprocess.TimeoutExpired, OSError):
        return []
    if out.returncode != 0:
        return []
    res: list[Path] = []
    for e in out.stdout.split(b"\x00"):
        if len(e) < 4:
            continue
        rel = e[3:].decode("utf-8", "replace")
        if rel:
            res.append(worktree / rel)
    return res


def unrecoverable_content(repo: Path, files: list[Path]) -> list[Path]:
    """Subset of `files` whose exact content is NOT in the repo object DB.

    Definitive recoverability test (worktrees share the object store). Fails
    SAFE: on any hiccup returns the whole candidate list (over-preserve).
    """
    files = [f for f in files if f.is_file()]
    if not files:
        return []
    try:
        hp = subprocess.run(
            ["git", "-C", str(repo), "hash-object", "--stdin-paths"],
            input="\n".join(str(f) for f in files).encode(),
            capture_output=True, timeout=300,
        )
        hashes = hp.stdout.decode().split()
        if hp.returncode != 0 or len(hashes) != len(files):
            return files
        cp = subprocess.run(
            ["git", "-C", str(repo), "cat-file", "--batch-check"],
            input="\n".join(hashes).encode(),
            capture_output=True, timeout=300,
        )
        present: dict[str, bool] = {}
        for line in cp.stdout.decode().splitlines():
            parts = line.split()
            if len(parts) >= 2:
                present[parts[0]] = parts[1] != "missing"
        return [f for f, h in zip(files, hashes) if not present.get(h, False)]
    except (subprocess.TimeoutExpired, OSError):
        return files


def snapshot_unrecoverable(main_repo: Path, worktree: Path, slug: str) -> tuple[int, int, bool]:
    """Snapshot genuinely-unsaved files before removal.

    Returns (snapshotted, recoverable_discarded, all_safe). all_safe is False
    only if a genuinely-unsaved file could NOT be copied — caller must then
    refuse to delete the worktree.
    """
    files = dirty_files(worktree)
    uniq = unrecoverable_content(main_repo, files)
    recoverable = len(files) - len(uniq)
    snap_root = snapshot_dir_for(main_repo) / slug
    snapped = 0
    all_safe = True
    for src in uniq:
        try:
            rel = src.relative_to(worktree)
        except ValueError:
            all_safe = False
            continue
        dst = snap_root / rel
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            snapped += 1
        except OSError:
            all_safe = False
    return snapped, recoverable, all_safe


def remove_worktree(main_repo: Path, worktree: Path, force: bool = True) -> bool:
    """`git worktree remove` (keeps the branch ref). True on success."""
    args = ["worktree", "remove"] + (["--force"] if force else []) + [str(worktree)]
    try:
        return git(main_repo, args).returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


def list_orphan_dirs(main_repo: Path) -> list[Path]:
    """Dirs under `.claude/worktrees/` that git no longer registers.

    These accumulate when a worktree's git registration is pruned (or never
    completed) but the directory is left on disk — each a full stale checkout.
    The cap/remove hooks only see REGISTERED worktrees (`git worktree list`),
    so orphan dirs are invisible to them and need this dedicated sweep. This
    is the gap that let the vault reach 19 orphan dirs even with the hooks live.
    """
    wt_dir = main_repo / WORKTREES_SEG
    if not wt_dir.is_dir():
        return []
    registered = {p.resolve() for p in list_worktrees(main_repo)}
    orphans: list[Path] = []
    try:
        for c in sorted(wt_dir.iterdir()):
            if c.is_dir() and c.resolve() not in registered:
                orphans.append(c)
    except OSError:
        return []
    return orphans


def _gitfile_target(orphan: Path) -> Path | None:
    """If `orphan/.git` is a `gitdir: <path>` pointer file, return <path>, else None.

    A worktree's `.git` is a one-line pointer file (not a dir). A relocation
    copies it verbatim, so it still points at the OLD location's gitdir.
    """
    gitfile = orphan / ".git"
    try:
        if not gitfile.is_file():
            return None
        txt = gitfile.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None
    if not txt.startswith("gitdir:"):
        return None
    target = txt[len("gitdir:"):].strip()
    if not target:
        return None
    p = Path(target)
    if not p.is_absolute():
        p = orphan / p
    return p


def _is_relocation_orphan(orphan: Path, main_repo: Path) -> bool:
    """True iff `orphan/.git` points at a gitdir that is DANGLING (gone) or
    EXTERNAL (outside this repo's `.git`) — the vault-relocation / copied-checkout
    class that `git status` can't evaluate but the MAIN object DB still can.

    Conservative: no clear pointer → False (keep, unknown provenance).
    """
    target = _gitfile_target(orphan)
    if target is None:
        return False
    try:
        main_git = (main_repo / ".git").resolve()
    except OSError:
        return False
    if not target.exists():
        return True  # dangling: original gitdir is gone (the relocation case)
    try:
        target.resolve().relative_to(main_git)
        return False  # inside this repo's own .git tree — a real registration
    except (ValueError, OSError):
        return True  # external: points at a different/foreign .git tree


def _reclaim_disconnected_orphan(main_repo: Path, orphan: Path, slug: str) -> tuple[str, int]:
    """Reclaim a relocation-orphan whose own git metadata is unusable.

    A worktree is a checkout of commits in the MAIN repo's shared object store,
    so `unrecoverable_content(main_repo, ...)` stays a definitive recoverability
    oracle even when the orphan's `.git` pointer is dead. Snapshot the
    genuinely-unique files (uncommitted work that survived the move), then remove.
    Fails SAFE: never deletes a file whose content isn't provably in the object DB
    (unrecoverable_content over-preserves on any hiccup), and never removes the
    dir if any unique file could not be copied out first.
    """
    files: list[Path] = []
    try:
        for root, dirs, fs in os.walk(orphan):
            dirs[:] = [d for d in dirs if d not in EXHAUST]
            for f in fs:
                if f in EXHAUST:  # skip the .git pointer file, .DS_Store, etc.
                    continue
                files.append(Path(root) / f)
    except OSError:
        return ("kept-unsafe", 0)
    uniq = unrecoverable_content(main_repo, files)
    snap_root = snapshot_dir_for(main_repo) / slug
    snapped = 0
    all_safe = True
    for src in uniq:
        if not src.is_file():
            continue
        try:
            rel = src.relative_to(orphan)
        except ValueError:
            all_safe = False
            continue
        dst = snap_root / rel
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            snapped += 1
        except OSError:
            all_safe = False
    if not all_safe:
        return ("kept-unsafe", snapped)
    try:
        shutil.rmtree(orphan)
    except OSError:
        return ("kept-unsafe", snapped)
    return ("relocation-orphan+removed" if snapped else "relocation-orphan-removed", snapped)


def reclaim_orphan_dir(main_repo: Path, orphan: Path, idle_min: int = 60) -> tuple[str, int]:
    """Safely reclaim one orphan worktree dir. Returns (action, snapshotted).

    action ∈ {removed, snapshot+removed, kept-active, kept-unsafe, kept-dangling,
              relocation-orphan-removed, relocation-orphan+removed}.

    Fast + fail-safe — never `rm -rf` a dir we can't reason about:
      * idle gate: a dir touched < idle_min ago is left (a live/paused session).
      * `git -C <orphan> status` decides recoverability cheaply (uses the index):
          - clean       → rm (every file is committed/recoverable from a branch)
          - dirty       → snapshot ONLY the dirty set (small; definitive object-DB
                          recoverability test) then rm iff every unsaved file was
                          safely copied.
          - git errors  → the dir is disconnected from git. If its `.git` pointer
                          is dangling/external (the vault-RELOCATION copied-checkout
                          class that let `.claude/worktrees` reach 100k+ files), the
                          MAIN repo's object DB is still a definitive recoverability
                          oracle: snapshot the genuinely-unique files, then remove.
                          Otherwise (unknown provenance) KEEP + report `kept-dangling`.

    Unlike the bash prune's section-2 (`rm -rf` with no snapshot), this can lose
    nothing: the only dirs deleted are clean checkouts or dirs whose unsaved
    files were copied out first.
    """
    slug = orphan.name
    if not is_idle(orphan, idle_min):
        return ("kept-active", 0)
    try:
        st = git(orphan, ["status", "--porcelain", "-z"], timeout=60)
        status_rc = st.returncode
    except (subprocess.TimeoutExpired, OSError):
        status_rc = -1
    if status_rc != 0:
        # git can't evaluate this dir. A relocation-orphan (dangling/external
        # .git pointer — copied during a vault move; original gitdir gone) is
        # still reclaimable against the MAIN object DB; anything else stays kept.
        if _is_relocation_orphan(orphan, main_repo):
            return _reclaim_disconnected_orphan(main_repo, orphan, slug)
        return ("kept-dangling", 0)
    dirty = [
        orphan / e[3:].decode("utf-8", "replace")
        for e in st.stdout.split(b"\x00")
        if len(e) >= 4 and e[3:]
    ]
    snapped = 0
    if dirty:
        uniq = unrecoverable_content(main_repo, dirty)
        snap_root = snapshot_dir_for(main_repo) / slug
        all_safe = True
        for src in uniq:
            if not src.is_file():
                continue
            try:
                rel = src.relative_to(orphan)
            except ValueError:
                all_safe = False
                continue
            dst = snap_root / rel
            try:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                snapped += 1
            except OSError:
                all_safe = False
        if not all_safe:
            return ("kept-unsafe", snapped)
    try:
        shutil.rmtree(orphan)
    except OSError:
        return ("kept-unsafe", snapped)
    return ("snapshot+removed" if snapped else "removed", snapped)


DRIVEFS_ROOTS_DB = (
    Path.home() / "Library/Application Support/Google/DriveFS/root_preference_sqlite.db"
)


def drive_mirror_root_paths(db_path: str | Path | None = None) -> list[str]:
    """Native-path Google Drive "Mirror" roots (sync_type=1) from the DriveFS DB.

    Mirror roots live at an arbitrary local path and never appear under
    ~/Library/CloudStorage, so a path-marker check cannot see them. This is the
    SINGLE source of that signal, shared by detect_cloud_sync (the install guard
    + the SessionStart footprint signal) and the check-sync-folder-machinery
    audit (MYC-1130) so they can never drift. Read FAIL-OPEN: a missing / locked
    / malformed DB returns [] and never raises. `immutable=1` so a LIVE Drive
    holding a write lock still reads (a plain `mode=ro` can return empty).
    """
    db = Path(db_path) if db_path is not None else DRIVEFS_ROOTS_DB
    if not db.exists():
        return []
    roots: list[str] = []
    try:
        con = sqlite3.connect(db.as_uri() + "?immutable=1", uri=True, timeout=2.0)
        try:
            cur = con.execute(
                "SELECT last_seen_absolute_path, root_path FROM roots "
                "WHERE sync_type = 1"
            )
            for last_seen, root_path in cur.fetchall():
                cand = (last_seen or "").strip() or (root_path or "").strip()
                if cand:
                    roots.append(cand)
        finally:
            con.close()
    except Exception:
        return []  # fail-open: a DB hiccup must never break the advisory guard
    return roots


def detect_cloud_sync(path: Path, *, _drivefs_db: str | Path | None = None) -> str | None:
    """Name of a consumer cloud-sync service whose scope contains `path`, else None.

    Cross-platform best-effort: a brain/vault under iCloud / OneDrive / Dropbox /
    Google Drive / Box is the exact combination that turns worktree churn into a
    machine-melting sync storm. The index belongs server-side; the local vault
    belongs on a real local disk, never in a consumer sync folder.

    `_drivefs_db` overrides the DriveFS roots-DB path for hermetic tests; in
    production it stays None and resolves to the real per-user location.
    """
    p = str(path.resolve())
    home = str(Path.home())
    markers = {
        "OneDrive": ["/OneDrive", "\\OneDrive"],
        "Dropbox": ["/Dropbox", "\\Dropbox"],
        "Google Drive": ["/Google Drive", "/GoogleDrive",
                          "CloudStorage/GoogleDrive", "\\Google Drive"],
        "Box": ["/Box/", "\\Box\\", "/Box Sync"],
        "iCloud Drive": ["/Mobile Documents/com~apple~CloudDocs",
                         "/Library/Mobile Documents"],
    }
    for name, subs in markers.items():
        if any(sub in p for sub in subs):
            return name
    # macOS iCloud "Desktop & Documents" sync: ~/Desktop or ~/Documents are
    # synced when ~/Library/Mobile Documents/com~apple~CloudDocs/<folder> exists.
    icloud = Path(home) / "Library/Mobile Documents/com~apple~CloudDocs"
    for folder in ("Desktop", "Documents"):
        try:
            base = (Path(home) / folder).resolve()
        except OSError:
            continue
        if (p == str(base) or p.startswith(str(base) + "/")) and (icloud / folder).exists():
            return f"iCloud Drive ({folder} sync)"
    # Native-path Google Drive "Mirror" roots (sync_type=1) are invisible to the
    # markers above; the DriveFS roots DB is the only signal (MYC-1130).
    # WORKTREE_SAFETY_DRIVEFS_DB overrides the DB path for hermetic tests of the
    # install-guard chain (check-cloud-sync.py has no _drivefs_db arg).
    for root in drive_mirror_root_paths(_drivefs_db or os.environ.get("WORKTREE_SAFETY_DRIVEFS_DB")):
        try:
            rp = str(Path(root).resolve())
        except OSError:
            continue
        if p == rp or p.startswith(rp + "/"):
            return "Google Drive (Mirror)"
    return None


def _obsidian_config_path(explicit: str | Path | None = None) -> Path | None:
    """Locate Obsidian's obsidian.json: explicit arg > $OBSIDIAN_CONFIG > per-OS
    default. Returns the explicit/env path verbatim (caller guards is_file); for
    the defaults, the first that exists, else None."""
    if explicit is not None:
        return Path(explicit)
    env = os.environ.get("OBSIDIAN_CONFIG")
    if env:
        return Path(env)
    home = Path.home()
    candidates = [
        home / "Library/Application Support/obsidian/obsidian.json",  # macOS
        home / ".config/obsidian/obsidian.json",                      # Linux
    ]
    appdata = os.environ.get("APPDATA")
    if appdata:
        candidates.append(Path(appdata) / "obsidian" / "obsidian.json")  # Windows
    candidates.append(home / "AppData/Roaming/obsidian/obsidian.json")
    for c in candidates:
        try:
            if c.is_file():
                return c
        except OSError:
            continue
    return None


def obsidian_vault_paths(config_path: str | Path | None = None) -> list[Path]:
    """Absolute paths of every vault Obsidian has registered, from obsidian.json.

    Lets the cloud-sync offer find a pre-existing Obsidian vault that was never
    pasted into guided setup — the "user already had an iCloud vault (Obsidian's
    common default)" case the SessionStart footprint signal otherwise misses (it
    only sees the vault you are cwd'd inside). Bounded + fail-open by construction:
    one small JSON read, never a filesystem walk, and [] on any missing /
    malformed / unreadable config — a registry hiccup must never break a hook.

    Schema: {"vaults": {"<id>": {"path": "<abs>", "open": bool, ...}, ...}}.
    """
    cfg = _obsidian_config_path(config_path)
    if cfg is None or not cfg.is_file():
        return []
    try:
        data = json.loads(cfg.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    vaults = data.get("vaults") if isinstance(data, dict) else None
    if not isinstance(vaults, dict):
        return []
    out: list[Path] = []
    seen: set[str] = set()
    for entry in vaults.values():
        if not isinstance(entry, dict):
            continue
        p = entry.get("path")
        if isinstance(p, str) and p and p not in seen:
            seen.add(p)
            out.append(Path(p))
    return out


# Optional session-liveness file written by session-lock.py (a sibling hook).
# Reading it lets the cap reaper distinguish "this scratch worktree belongs to a
# session that is still running" from "its session is gone" — so a crashed
# session's worktree can be reclaimed promptly (regardless of the count cap)
# while a live-but-idle session's worktree is never pulled out from under it.
SESSION_LOCK_REL = ".claude/.session-lock.json"


def _pid_alive(pid: int) -> bool:
    """True if `pid` names a running process. Errs toward 'alive' (over-preserve)."""
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists, owned by another uid
    except OSError:
        return True  # unsure → treat as alive so we never reap a maybe-live session


def live_session_cwds(main_repo: Path, grace_min: int = 35) -> set[str] | None:
    """Resolved cwd paths of currently-LIVE Claude sessions, from the session lock.

    A session counts as live if its PID is running OR it was active within the
    last `grace_min` minutes (the lock prunes idle entries at ~30 min, so 35 min
    gives a margin). Both checks err toward "live" — the only safe direction,
    since the consumer uses this to decide what NOT to reclaim.

    Returns None when liveness is UNKNOWN (lock absent / unreadable / wrong shape).
    None is distinct from an empty set: callers MUST treat None as "do not reap on
    liveness" (never interpret a missing lock as "no sessions are live → reap all").
    """
    lock = main_repo / SESSION_LOCK_REL
    try:
        data = json.loads(lock.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    sessions = data.get("sessions") if isinstance(data, dict) else None
    if not isinstance(sessions, dict):
        return None
    cutoff = time.time() - grace_min * 60
    live: set[str] = set()
    for s in sessions.values():
        if not isinstance(s, dict):
            continue
        cwd = s.get("cwd")
        if not cwd:
            continue
        la = s.get("last_activity_at")
        recent = isinstance(la, (int, float)) and la >= cutoff
        if recent or _pid_alive(s.get("pid")):
            try:
                live.add(str(Path(cwd).resolve()))
            except OSError:
                live.add(str(cwd))
    return live
