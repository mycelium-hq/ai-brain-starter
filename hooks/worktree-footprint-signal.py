#!/usr/bin/env python3
"""Observe local footprint before it bloats — SessionStart signal.

The 102-worktree pileup was discovered only when the machine fell over. That
is the real failure: it was invisible until catastrophic. This hook makes the
footprint observable at every SessionStart so "12 worktrees and climbing" is
seen early, not "102, machine dead" later. Cheap: a couple of git/stat calls,
no per-worktree filesystem walk.

Surfaces (only when something warrants attention — silent when healthy):
  * worktree count over the soft threshold (WORKTREE_WARN, default 8)
  * on-disk worktree dirs git no longer tracks (orphans)
  * low free disk on the vault's volume
  * THE DANGEROUS COMBO: vault sitting inside a consumer cloud-sync folder
    (iCloud / OneDrive / Dropbox / Google Drive / Box) — worktree/.git churn
    there is what melts the sync daemon. Flagged loudly with the remedy.

Bypass: WORKTREE_FOOTPRINT_BYPASS=1.

WIRING (SessionStart):
  "SessionStart": [
    {"hooks": [{
      "type": "command",
      "command": "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/worktree-footprint-signal.py 2>/dev/null || echo '{\"continue\":true,\"suppressOutput\":true}'"
    }]}
  ]
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

HOOK_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(HOOK_DIR))

from _lib.worktree_safety import (  # noqa: E402
    WORKTREES_SEG,
    detect_cloud_sync,
    find_main_repo,
    is_scratch_worktree,
    list_worktrees,
)

DEFAULT_WARN = 8
DEFAULT_FREE_GB = 5.0


def _emit(ctx: str | None) -> int:
    if ctx:
        print(json.dumps({"continue": True, "additionalContext": ctx}))
    else:
        print(json.dumps({"continue": True, "suppressOutput": True}))
    return 0


def main() -> int:
    if os.environ.get("WORKTREE_FOOTPRINT_BYPASS") == "1":
        return _emit(None)

    main_repo = find_main_repo()
    if main_repo is None:
        return _emit(None)

    try:
        warn_at = max(1, int(os.environ.get("WORKTREE_WARN", DEFAULT_WARN)))
    except ValueError:
        warn_at = DEFAULT_WARN
    try:
        free_floor = float(os.environ.get("WORKTREE_FREE_GB", DEFAULT_FREE_GB))
    except ValueError:
        free_floor = DEFAULT_FREE_GB

    # Count only scratch worktrees for the cap warning; deliberate sibling
    # worktrees (~/dev/<repo>-<slug>) are not part of the pileup problem.
    registered = sum(1 for w in list_worktrees(main_repo) if is_scratch_worktree(w))

    wt_dir = main_repo / WORKTREES_SEG
    on_disk = 0
    if wt_dir.is_dir():
        try:
            on_disk = sum(1 for c in wt_dir.iterdir() if c.is_dir())
        except OSError:
            on_disk = 0
    orphans = max(0, on_disk - registered)

    free_gb = None
    try:
        free_gb = shutil.disk_usage(main_repo).free / 1024 ** 3
    except OSError:
        pass

    cloud = detect_cloud_sync(main_repo)

    lines: list[str] = []

    # Fire on ANY git-backed vault inside cloud sync — not only once worktrees
    # exist. A fresh iCloud install with zero worktrees is ALREADY dangerous: the
    # `.git/` rewrites on every commit and the sync daemon chokes on that alone
    # (the .git-in-mirror variant). Catching it at first SessionStart beats
    # catching it after the machine is already churning.
    has_git = (main_repo / ".git").exists()
    if cloud and (has_git or registered or on_disk):
        if on_disk:
            wt_note = f"it has {on_disk} worktree checkout(s); "
        else:
            wt_note = "even with zero worktrees its `.git/` rewrites on every commit; "
        lines.append(
            f"⚠️  [footprint] This vault is inside **{cloud}** — {wt_note}"
            f"consumer cloud-sync + git churn = the sync-storm failure mode "
            f"(millions of file events, pegged CPU, frozen machine). The vault "
            f"belongs on a local disk; the index belongs server-side. Move it out "
            f"of the sync folder (see docs/CLOUD_SYNC.md), or at minimum keep "
            f"`.claude/`, `.git/`, `.smart-env/` out of sync scope."
        )

    if registered > warn_at or orphans > 0:
        bits = [f"{registered} registered worktree(s) (soft cap {warn_at})"]
        if orphans:
            bits.append(f"{orphans} orphan dir(s) git no longer tracks")
        lines.append(
            f"[footprint] {'; '.join(bits)}. Each worktree is ~a full checkout. "
            f"They auto-trim at SessionEnd + via the cap; force now with "
            f"`python3 scripts/worktree-prune.sh` or the reclaim tool."
        )

    if free_gb is not None and free_gb < free_floor:
        lines.append(f"⚠️  [footprint] Low free disk: {free_gb:.1f} GB on the vault volume.")

    return _emit("\n".join(lines) if lines else None)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        print(json.dumps({"continue": True, "suppressOutput": True}))
        sys.exit(0)
