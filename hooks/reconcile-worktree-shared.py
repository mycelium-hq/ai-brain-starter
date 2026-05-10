#!/usr/bin/env python3
"""SessionEnd hook: reconcile worktree's shared-canonical files against main vault.

Wire into ~/.claude/settings.json SessionEnd hooks so it runs every session close.

Problem this fixes:
- When you use git worktrees inside an Obsidian vault and have a PreToolUse
  guard that routes "shared-canonical" file edits (e.g. .claude/hookify.*.local.md)
  to MAIN VAULT path, the worktree's filesystem copy gets synced (via cp / auto-
  commit hooks) but the worktree's GIT INDEX never gets updated.
- Result: `git status` in the worktree shows `M` / `??` for files that are
  already preserved at main vault. Worktree-archive UI fires "N uncommitted
  changes will be discarded" warnings on every session close.
- The warning is a false positive but trains the eye to ignore it, which would
  mask a real loss the day a worktree edit ISN'T also at main.

This hook detects identical-to-main shared-canonical files and stages+commits
them on the worktree branch silently. Real divergences are surfaced for human
review and left alone.

CONFIG (per user, once):
1. Set VAULT_ROOT below to your vault root, OR rely on auto-detect (walks up
   from cwd looking for the .claude/worktrees/ pattern).
2. Edit SHARED_PATTERNS to match your worktree-discipline rules.
3. Wire into ~/.claude/settings.json:
     "SessionEnd": [
       {"matcher": "", "hooks": [{
         "type": "command",
         "command": "python3 ~/.claude/hooks/reconcile-worktree-shared.py 2>/dev/null || echo '{\"continue\":true,\"suppressOutput\":true}'"
       }]}
     ]

BYPASS: WORKTREE_RECONCILE_BYPASS=1
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

# Glob patterns of shared-canonical files (relative to worktree root).
# Add patterns matching your own worktree-edit-discipline rules.
SHARED_PATTERNS = [
    ".claude/hookify.*.local.md",
    # Common candidates to add as the same false-warning surfaces:
    # "⚙️ Meta/rules/*.md",
    # "scripts/*.py",
    # "scripts/*.sh",
    # ".mcp.json",
    # "CLAUDE.md",
]


def find_main_vault(cwd: Path) -> Path | None:
    """Walk up cwd looking for the parent that contains .claude/worktrees/<this-slug>/.

    Returns the parent (i.e. the main vault root). Returns None if not in a worktree.
    """
    parts = cwd.parts
    try:
        idx = parts.index(".claude")
    except ValueError:
        return None
    if len(parts) <= idx + 1 or parts[idx + 1] != "worktrees":
        return None
    return Path(*parts[:idx])


def worktree_root(cwd: Path) -> Path | None:
    """Return the worktree root (.../.claude/worktrees/<slug>/), or None."""
    parts = cwd.parts
    try:
        idx = parts.index(".claude")
        if len(parts) > idx + 2 and parts[idx + 1] == "worktrees":
            return Path(*parts[: idx + 3])
    except ValueError:
        pass
    return None


def files_identical(a: Path, b: Path) -> bool:
    try:
        return a.read_bytes() == b.read_bytes()
    except (OSError, UnicodeDecodeError):
        return False


def main() -> None:
    if os.environ.get("WORKTREE_RECONCILE_BYPASS"):
        return

    try:
        sys.stdin.read()
    except Exception:
        pass

    cwd = Path.cwd()
    main_vault = find_main_vault(cwd)
    wt = worktree_root(cwd)

    if main_vault is None or wt is None:
        return  # Not in a worktree, nothing to reconcile

    reconciled: list[str] = []
    divergent: list[str] = []

    for pattern in SHARED_PATTERNS:
        for wt_file in wt.glob(pattern):
            rel = wt_file.relative_to(wt)
            main_file = main_vault / rel
            if not main_file.exists():
                continue
            if not files_identical(wt_file, main_file):
                divergent.append(str(rel))
                continue
            res = subprocess.run(
                ["git", "-C", str(wt), "add", "--", str(rel)],
                capture_output=True,
            )
            if res.returncode == 0:
                reconciled.append(str(rel))

    if not reconciled:
        return

    msg = (
        f"auto: reconcile-worktree-shared synced {len(reconciled)} "
        f"shared-canonical file(s) to match main vault\n\n"
        + "\n".join(f"- {f}" for f in reconciled)
    )
    res = subprocess.run(
        ["git", "-C", str(wt), "commit", "-m", msg, "--quiet"],
        capture_output=True,
    )
    if res.returncode == 0:
        print(json.dumps({
            "systemMessage": (
                f"[reconcile-worktree-shared] auto-staged + committed "
                f"{len(reconciled)} shared-canonical file(s) on worktree "
                f"that already matched main vault."
            )
        }))

    if divergent:
        print(json.dumps({
            "systemMessage": (
                f"[reconcile-worktree-shared] {len(divergent)} shared-canonical "
                f"file(s) DIVERGE from main vault: {', '.join(divergent[:5])}"
            )
        }), file=sys.stderr)


if __name__ == "__main__":
    main()
