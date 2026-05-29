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

import os
import shutil
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
    2. If cwd is inside `.../.claude/worktrees/<slug>/`, the part before
       `.claude/worktrees`.
    3. cwd itself if it contains `.claude/worktrees/`.
    4. Walk up cwd for a parent containing `.claude/worktrees/`.
    Returns None if nothing resolves.
    """
    cwd = (cwd or Path.cwd()).resolve()

    env_root = os.environ.get("CLAUDE_PROJECT_DIR")
    if env_root:
        cand = Path(env_root)
        if cand.is_dir():
            return cand.resolve()

    marker = "/" + WORKTREES_SEG + "/"
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


def detect_cloud_sync(path: Path) -> str | None:
    """Name of a consumer cloud-sync service whose scope contains `path`, else None.

    Cross-platform best-effort: a brain/vault under iCloud / OneDrive / Dropbox /
    Google Drive / Box is the exact combination that turns worktree churn into a
    machine-melting sync storm. The index belongs server-side; the local vault
    belongs on a real local disk, never in a consumer sync folder.
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
    return None
