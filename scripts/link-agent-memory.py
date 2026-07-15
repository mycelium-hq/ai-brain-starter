#!/usr/bin/env python3
"""Make Claude Code's per-project memory physically live inside the vault.

THE PROBLEM THIS FIXES
----------------------
Claude Code writes its persistent memory (``MEMORY.md`` + topic files) to
``~/.claude/projects/<encoded-vault>/memory/`` — a per-account, per-machine,
tool-specific directory that is invisible inside Obsidian. For a product whose
entire premise is "your second brain lives in your vault", memory stranded in
``~/.claude/`` is a broken promise: it does not show up in the vault, it is not
in the vault's git history, and it does not survive switching machines or tools.

The substrate already assumed a symlink from that dir into the vault
(``instinct_lib.py`` looks for it, ``relocate-vault.sh`` re-homes it, tests
check it) — but nothing in the install ever CREATED it. This script is that
missing step.

WHAT IT DOES (idempotent, loss-free, never deletes)
---------------------------------------------------
1. Ensures ``<vault>/⚙️ Meta/Agent Memory/`` exists (the vault-side home).
2. Resolves the Claude Code project-memory path for this vault.
3. If that path is a real directory with content, MIGRATES every file into the
   vault dir without loss (same-name-but-different files are kept as
   ``<name>.from-tooldir``), then backs the directory up to
   ``memory.pre-link-backup[-N]`` — never deletes — and replaces it with a
   link.
4. If it is missing, creates the link directly.
5. If it is already the correct link, no-ops.
6. Verifies the end state and FAILS LOUD if the link does not resolve to the
   vault dir — a wrong-key silent no-op is the worst outcome.

The link is a symlink on POSIX and a directory JUNCTION on Windows: a real
symlink there needs admin rights or Developer Mode (``symlink_to`` dies with
``WinError 1314`` for normal users), while junctions need no privilege and
Obsidian, git, and Python all traverse them like normal directories. Junction
targets must be absolute local paths — the vault dir here always is.

After this runs, everything Claude Code "remembers" is a file in the user's
vault, visible in Obsidian and tracked by the vault's git.

Usage:
    python3 scripts/link-agent-memory.py --vault "/path/to/vault"
    python3 scripts/link-agent-memory.py --vault "/path/to/vault" --dry-run
"""

from __future__ import annotations

import argparse
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _project_key import project_dir_for  # noqa: E402

AGENT_MEMORY_RELPATH = ("⚙️ Meta", "Agent Memory")


def _say(msg: str, quiet: bool) -> None:
    if not quiet:
        print(msg)


def _is_link(p: Path) -> bool:
    """Symlink on any OS, or an NTFS directory junction on Windows.

    Junctions are what this script creates on Windows, but ``is_symlink()`` is
    False for them (they are mount-point reparse points, not symlinks), so the
    idempotency / verify / refuse-to-clobber checks must read the reparse tag.
    """
    if p.is_symlink():
        return True
    if os.name != "nt":
        return False
    try:
        st = os.lstat(p)
    except OSError:
        return False
    return getattr(st, "st_reparse_tag", 0) == stat.IO_REPARSE_TAG_MOUNT_POINT


def _same_target(link: Path, target: Path) -> bool:
    try:
        return _is_link(link) and Path(os.path.realpath(link)) == Path(os.path.realpath(target))
    except OSError:
        return False


def _make_dir_link(link: Path, target: Path) -> None:
    """Create ``link`` as a directory link pointing at ``target``.

    POSIX: a symlink. Windows: a directory junction — ``symlink_to`` there
    raises ``WinError 1314`` unless the process is elevated or Developer Mode
    is on, while junctions need no privilege at all.
    """
    if os.name != "nt":
        link.symlink_to(target, target_is_directory=True)
        return
    try:
        import _winapi  # CPython-private but long-stable; ships CreateJunction
    except ImportError:
        _winapi = None
    if _winapi is not None and hasattr(_winapi, "CreateJunction"):
        _winapi.CreateJunction(str(target), str(link))
        return
    # Non-CPython Windows fallback: cmd's mklink /J creates the same junction.
    subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(target)],
        check=True,
        capture_output=True,
    )


def _migrate_contents(src_dir: Path, dst_dir: Path, *, dry_run: bool, quiet: bool) -> int:
    """Copy every file from src into dst without loss. Returns files migrated."""
    moved = 0
    for item in sorted(src_dir.rglob("*")):
        # Only migrate real files. Skip symlinks so a stray link in the source
        # never copies its target's content into the vault (defense-in-depth —
        # the source is Claude Code's own memory, but be strict anyway).
        if item.is_symlink() or not item.is_file():
            continue
        rel = item.relative_to(src_dir)
        dest = dst_dir / rel
        if dest.exists():
            if dest.read_bytes() == item.read_bytes():
                continue  # identical — nothing to do
            dest = dest.with_name(dest.name + ".from-tooldir")  # conflict — keep both
        if dry_run:
            _say(f"  would migrate: {rel} -> {dest.relative_to(dst_dir.parent)}", quiet)
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, dest)
        moved += 1
    return moved


def _backup_path(mem: Path) -> Path:
    base = mem.with_name("memory.pre-link-backup")
    if not base.exists():
        return base
    n = 2
    while base.with_name(f"memory.pre-link-backup-{n}").exists():
        n += 1
    return base.with_name(f"memory.pre-link-backup-{n}")


def link_agent_memory(vault: str, *, dry_run: bool = False, quiet: bool = False) -> Path:
    vault_path = Path(os.path.abspath(os.path.expanduser(vault)))
    if not vault_path.is_dir():
        raise SystemExit(f"link-agent-memory: vault is not a directory: {vault_path}")
    if not (vault_path / ".obsidian").exists():
        _say(f"  note: {vault_path} has no .obsidian/ — linking anyway", quiet)

    agent_mem = vault_path.joinpath(*AGENT_MEMORY_RELPATH)
    if dry_run:
        _say(f"  would ensure vault memory home: {agent_mem}", quiet)
    else:
        agent_mem.mkdir(parents=True, exist_ok=True)

    proj_dir = project_dir_for(vault_path)
    mem = proj_dir / "memory"

    # Already correctly linked -> nothing to do.
    if _same_target(mem, agent_mem):
        _say(f"✓ already linked: {mem} -> {agent_mem}", quiet)
        return mem

    # A link (symlink/junction) pointing somewhere ELSE -> do not clobber; fail loud.
    if _is_link(mem):
        current = os.path.realpath(mem)
        raise SystemExit(
            f"link-agent-memory: {mem} is already a link to {current}, not the vault's "
            f"Agent Memory ({agent_mem}). Refusing to clobber. Resolve by hand."
        )

    # A real directory -> migrate contents into the vault, back it up, replace.
    if mem.exists():
        moved = _migrate_contents(mem, agent_mem, dry_run=dry_run, quiet=quiet)
        backup = _backup_path(mem)
        if dry_run:
            _say(f"  would migrate {moved} file(s), back up {mem} -> {backup}, then link", quiet)
            _say(f"  would link: {mem} -> {agent_mem}", quiet)
            return mem
        mem.rename(backup)
        _say(f"  migrated {moved} file(s) into the vault; backed up old dir -> {backup.name}", quiet)
    elif dry_run:
        _say(f"  would link: {mem} -> {agent_mem}", quiet)
        return mem

    proj_dir.mkdir(parents=True, exist_ok=True)
    _make_dir_link(mem, agent_mem)

    # Verify — a wrong-key / failed link is a silent brain-loss bug. Fail loud.
    if not _same_target(mem, agent_mem):
        raise SystemExit(
            f"link-agent-memory: VERIFY FAILED — {mem} does not resolve to {agent_mem}. "
            f"Memory would NOT reach the vault. Aborting."
        )
    _say(f"✓ linked: {mem} -> {agent_mem}", quiet)
    _say("  Claude Code's memory now lives in your vault (visible in Obsidian, tracked by git).", quiet)
    return mem


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Link Claude Code project memory into the vault (symlink on POSIX, junction on Windows)."
    )
    ap.add_argument("--vault", required=True, help="Absolute path to the Obsidian vault.")
    ap.add_argument("--dry-run", action="store_true", help="Show what would happen; change nothing.")
    ap.add_argument("--quiet", action="store_true", help="Only print on error.")
    args = ap.parse_args()
    link_agent_memory(args.vault, dry_run=args.dry_run, quiet=args.quiet)
    return 0


if __name__ == "__main__":
    # Windows cp1252-console safety (#313): force UTF-8 so a non-ASCII print can't crash.
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8")  # Python 3.7+
        except (AttributeError, ValueError):
            pass
    raise SystemExit(main())
