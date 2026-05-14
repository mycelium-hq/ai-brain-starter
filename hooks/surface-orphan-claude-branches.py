#!/usr/bin/env python3
"""SessionStart hook: surface count of orphan claude/* branches in the vault.

Observability layer for the worktree branch loss bug class (issue #65 + PR #68).
PR #66 prevents new orphans from accumulating via two mechanisms:
- `session-end-hook.sh` routes commits to main vault (resolve_main_vault).
- `worktree-prune.sh` refuses to delete branches with unmerged commits.

PR #68 prevents the reconcile-noise class via `git merge --ff-only` first.

This hook closes the observability gap: at session start, count orphan
`claude/*` branches (branches with commits not reachable from master/main)
and surface the count if nonzero. Without it, future regressions in the
worktree-routing fixes would be silent — the failure mode is "user notices
six months later when something else breaks."

Output: silent if no orphans. Single-line systemMessage if any exist,
pointing at `scripts/recover-orphan-claude-branches.py` for recovery.

Performance: <100ms even with hundreds of branches.

Bypass: ORPHAN_SURFACE_BYPASS=1 in env.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def find_vault_root(cwd: Path) -> Path | None:
    """Walk up to find vault root (a directory with .git/ and a Meta-ish folder)."""
    # If we're inside a worktree, reset to main vault first.
    parts = cwd.parts
    if ".claude" in parts:
        idx = parts.index(".claude")
        if idx + 1 < len(parts) and parts[idx + 1] == "worktrees":
            if idx > 0:
                cwd = Path(*parts[:idx])

    p = cwd.resolve()
    for _ in range(8):
        if not p.is_dir():
            break
        # Vault root has .git/ AND a Meta folder (possibly with emoji prefix)
        if (p / ".git").exists():
            for child in p.iterdir():
                if child.is_dir() and child.name.endswith("Meta"):
                    return p
        parent = p.parent
        if parent == p:
            break
        p = parent
    return None


def detect_base_branch(vault: Path) -> str | None:
    """Return master or main, whichever the vault uses."""
    for candidate in ("master", "main"):
        r = subprocess.run(
            ["git", "-C", str(vault), "show-ref", "--verify", "--quiet", f"refs/heads/{candidate}"],
            capture_output=True,
        )
        if r.returncode == 0:
            return candidate
    return None


def count_orphans(vault: Path, base: str) -> tuple[int, int]:
    """Return (branch_count, total_unmerged_commit_count)."""
    out = subprocess.run(
        ["git", "-C", str(vault), "for-each-ref", "--format=%(refname:short)", "refs/heads/claude/"],
        capture_output=True,
        text=True,
    )
    if out.returncode != 0:
        return (0, 0)
    branches = [b.strip() for b in out.stdout.split() if b.strip()]
    n_branches = 0
    total_commits = 0
    for b in branches:
        r = subprocess.run(
            ["git", "-C", str(vault), "rev-list", "--count", f"{base}..{b}"],
            capture_output=True,
            text=True,
        )
        try:
            c = int(r.stdout.strip())
        except (ValueError, AttributeError):
            c = 0
        if c > 0:
            n_branches += 1
            total_commits += c
    return (n_branches, total_commits)


def main() -> int:
    if os.environ.get("ORPHAN_SURFACE_BYPASS"):
        return 0

    # SessionStart hook receives JSON on stdin
    try:
        sys.stdin.read()
    except Exception:
        pass

    vault = find_vault_root(Path.cwd())
    if vault is None:
        return 0

    base = detect_base_branch(vault)
    if base is None:
        return 0

    n_branches, total_commits = count_orphans(vault, base)
    if n_branches == 0:
        return 0

    msg = (
        f"[orphan-branches] {n_branches} `claude/*` branch(es) with "
        f"{total_commits} unmerged commit(s) vs {base}. "
        f"Run `python3 scripts/recover-orphan-claude-branches.py --dry-run` "
        f"to inspect, then drop `--dry-run` to fast-forward FF-able branches."
    )
    print(json.dumps({"systemMessage": msg}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
