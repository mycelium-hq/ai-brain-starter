#!/usr/bin/env python3
"""sync-skills.py — propagate skill updates from the ai-brain-starter repo
into the user's installed ~/.claude/skills/ directory.

Cross-platform (macOS / Linux / Windows) successor to sync-skills.sh, which is
now a thin delegator to this file. The bash version could not run on native
Windows, so Windows installs never received skill-content updates after a pull.

Runs after `git pull` on the starter repo. For each skill bundled under
skills/, syncs every file into the corresponding installed skill folder. Never
destroys user customizations without recovery: any installed file that differs
from the incoming repo file is backed up to <file>.bak-YYYY-MM-DD-HHMM before
being overwritten.

Honors the NEVER-fail-silently rule: writes a structured summary to the
starter repo's .sync.log and prints it to stdout so the session-start hook can
surface it to Claude (who surfaces it to the user).

Skip guards (all preserved from the shell version):
  - Installed skill dir is a symlink        -> managed elsewhere, skip.
  - Installed skill dir has its own .git    -> independently managed fork, skip.
  - Destination file (or a parent dir) is a symlink -> maintainer workflow, skip.

Env overrides for hermetic tests: ABS_SYNC_STARTER_DIR, ABS_SYNC_INSTALL_DIR.

Usage: python3 ~/.claude/skills/ai-brain-starter/scripts/sync-skills.py
Exit:  0 clean, 2 if any file operation errored (so the hook can surface it).
"""

from __future__ import annotations

import filecmp
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path


def _starter_dir() -> Path:
    return Path(os.environ.get("ABS_SYNC_STARTER_DIR")
                or (Path.home() / ".claude" / "skills" / "ai-brain-starter"))


def _install_dir() -> Path:
    return Path(os.environ.get("ABS_SYNC_INSTALL_DIR")
                or (Path.home() / ".claude" / "skills"))


class SyncReport:
    def __init__(self) -> None:
        self.created: list[str] = []
        self.updated: list[str] = []
        self.backed_up: list[str] = []
        self.skipped: list[str] = []
        self.errors: list[str] = []


def _any_symlink(path: Path, levels: int = 3) -> bool:
    """True if the path or up to `levels-1` of its parents is a symlink.
    Mirrors the shell guard: never follow a symlinked destination — a
    symlinked install means a maintainer manages the skill upstream, and
    writing through it would clobber their private working tree."""
    p = path
    for _ in range(levels):
        if p.is_symlink():
            return True
        p = p.parent
    return False


def sync_file(src: Path, dest: Path, skill_name: str, stamp: str, r: SyncReport) -> None:
    if not src.is_file():
        return
    if _any_symlink(dest):
        r.skipped.append(f"{skill_name}: {dest.name} (symlinked install, maintainer workflow)")
        return
    if dest.is_file():
        if filecmp.cmp(str(src), str(dest), shallow=False):
            return  # identical — no-op, no noise
        bak = dest.with_name(dest.name + f".bak-{stamp}")
        try:
            shutil.copy2(str(dest), str(bak))
            r.backed_up.append(str(bak))
        except OSError:
            r.errors.append(f"could not back up {dest} before overwrite")
            return
        try:
            shutil.copy2(str(src), str(dest))
            r.updated.append(f"{skill_name}: {dest.name}")
        except OSError:
            r.errors.append(f"could not overwrite {dest} (backup still at {bak})")
    else:
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(src), str(dest))
            r.created.append(f"{skill_name}: {dest.name}")
        except OSError:
            r.errors.append(f"could not create {dest}")


def sync_skill_folder(source_dir: Path, dest_dir: Path, skill_name: str,
                      stamp: str, r: SyncReport) -> None:
    if not source_dir.is_dir():
        return
    if dest_dir.is_symlink():
        r.skipped.append(f"{skill_name}: {dest_dir} is a symlink (managed elsewhere)")
        return
    # An installed skill with its own .git is an independently managed fork —
    # overwriting from the starter would clobber the user's commits.
    if (dest_dir / ".git").exists():
        r.skipped.append(f"{skill_name}: {dest_dir} has its own git repo (independently managed)")
        return
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        r.errors.append(f"could not create {dest_dir}")
        return
    for root, _dirs, files in os.walk(str(source_dir)):
        for name in files:
            src_file = Path(root) / name
            rel = src_file.relative_to(source_dir)
            sync_file(src_file, dest_dir / rel, skill_name, stamp, r)


def main() -> int:
    starter = _starter_dir()
    install = _install_dir()
    stamp = time.strftime("%Y-%m-%d-%H%M")
    if not starter.is_dir():
        print(f"ERROR: ai-brain-starter repo not found at {starter}", file=sys.stderr)
        return 1
    try:
        install.mkdir(parents=True, exist_ok=True)
    except OSError:
        print(f"ERROR: could not create install dir {install}", file=sys.stderr)
        return 1

    r = SyncReport()
    skills_root = starter / "skills"
    if skills_root.is_dir():
        for skill_dir in sorted(skills_root.iterdir()):
            if skill_dir.is_dir():
                sync_skill_folder(skill_dir, install / skill_dir.name,
                                  skill_dir.name, stamp, r)

    lines = [
        f"=== sync-skills run at {stamp} ===",
        f"Created: {len(r.created)} file(s)",
        *[f"  + {f}" for f in r.created],
        f"Updated: {len(r.updated)} file(s)",
        *[f"  ~ {f}" for f in r.updated],
        f"Backed up: {len(r.backed_up)} file(s) (local customizations preserved)",
        *[f"  b {f}" for f in r.backed_up],
        f"Skipped: {len(r.skipped)} skill(s)",
        *[f"  s {f}" for f in r.skipped],
        f"Errors: {len(r.errors)}",
        *[f"  ! {f}" for f in r.errors],
        "",
    ]
    summary = "\n".join(lines)
    print(summary)
    try:
        with (starter / ".sync.log").open("a", encoding="utf-8") as fh:
            fh.write(summary + "\n")
    except OSError:
        pass

    # --- Also refresh the vault's own <meta>/scripts/ (the skill->vault half) ---
    # sync-skills syncs skill -> ~/.claude/skills; sync-vault-scripts.sh is the
    # other half that previously went stale because <meta>/scripts/ was only ever
    # populated at setup. It self-resolves the vault (--vault / $VAULT_ROOT /
    # settings.json) and is a non-fatal no-op when none is set up. Best-effort by
    # design: a vault-side hiccup (or no bash, e.g. native Windows) must NEVER
    # flip this script's exit code, so failures are swallowed.
    vault_sync = starter / "scripts" / "sync-vault-scripts.sh"
    if vault_sync.is_file():
        try:
            proc = subprocess.run(
                ["bash", str(vault_sync), "--quiet"],
                capture_output=True,
                text=True,
            )
            for line in (proc.stdout or "").splitlines():
                print(f"[vault-scripts] {line}")
        except (OSError, subprocess.SubprocessError):
            pass  # bash missing (Windows) or spawn failure — non-fatal by design

    return 2 if r.errors else 0


if __name__ == "__main__":
    sys.exit(main())
