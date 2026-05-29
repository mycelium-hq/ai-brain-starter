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

    registered = len(list_worktrees(main_repo))

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

    if cloud and (registered or on_disk):
        lines.append(
            f"⚠️  [footprint] This vault is inside **{cloud}**, and it has "
            f"{on_disk} worktree checkout(s). Consumer cloud-sync + churning git "
            f"worktrees = the sync-storm failure mode (millions of files, pegged "
            f"CPU). The vault belongs on a local disk; the index belongs "
            f"server-side. Move it out of the sync folder (see docs/CLOUD_SYNC.md), "
            f"or at minimum keep `.claude/`, `.git/`, `.smart-env/` out of sync scope."
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
