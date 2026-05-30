#!/usr/bin/env python3
"""Bound the number of git worktrees — reclaim-then-allow, at SessionStart.

The session-end removal hook (remove-ended-worktree.py) keeps the count low in
the normal case. This is the BACKSTOP for the abnormal case: a session that
crashes or is killed before SessionEnd fires leaves its worktree behind. Over
enough crashes those accumulate again. This hook caps the total.

DESIGN: reclaim-then-ALLOW, never block.
  Power users run many concurrent sessions; a hard block on worktree creation
  would break that workflow. So instead of blocking, when a new session starts
  and the count is over the cap, we reclaim the OLDEST idle `claude/<slug>`
  scratch worktrees (snapshotting any genuinely-unsaved content first, keeping
  branch refs) until back under the cap. Active worktrees (touched <60min),
  the current session's worktree, and deliberate feature-branch worktrees are
  never touched. If everything over the cap is active, we surface a note and
  leave them — correctness over the cap.

Cap:    WORKTREE_MAX env (default 12).
Bypass: WORKTREE_CAP_BYPASS=1.

WIRING (SessionStart):
  "SessionStart": [
    {"hooks": [{
      "type": "command",
      "command": "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/enforce-worktree-cap.py 2>/dev/null || echo '{\"continue\":true,\"suppressOutput\":true}'"
    }]}
  ]
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

HOOK_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(HOOK_DIR))

from _lib.worktree_safety import (  # noqa: E402
    current_worktree,
    find_main_repo,
    git,
    is_idle,
    is_scratch_worktree,
    list_worktrees,
    remove_worktree,
    snapshot_unrecoverable,
)

LOG_REL = "⚙️ Meta/logs/worktree-cleanup.log"
DEFAULT_CAP = 12


def _log(main_repo: Path, msg: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        log = main_repo / LOG_REL
        log.parent.mkdir(parents=True, exist_ok=True)
        with open(log, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] cap: {msg}\n")
    except OSError:
        pass


def _emit(ctx: str | None) -> int:
    if ctx:
        print(json.dumps({"continue": True, "additionalContext": ctx}))
    else:
        print(json.dumps({"continue": True, "suppressOutput": True}))
    return 0


def _branch(wt: Path) -> str:
    try:
        return git(wt, ["rev-parse", "--abbrev-ref", "HEAD"], timeout=15).stdout.decode().strip()
    except Exception:
        return ""


def main() -> int:
    if os.environ.get("WORKTREE_CAP_BYPASS") == "1":
        return _emit(None)

    try:
        cap = max(1, int(os.environ.get("WORKTREE_MAX", DEFAULT_CAP)))
    except ValueError:
        cap = DEFAULT_CAP

    main_repo = find_main_repo()
    if main_repo is None:
        return _emit(None)

    # Only SCRATCH worktrees (under .claude/worktrees/) count against the cap
    # and are eligible for reclaim. Deliberate ~/dev/<repo>-<slug> sibling
    # worktrees are never auto-removed, even when idle and on a claude/* branch.
    wts = [w for w in list_worktrees(main_repo) if is_scratch_worktree(w)]
    if len(wts) <= cap:
        return _emit(None)  # healthy

    cur = current_worktree()
    cur_path = cur[0].resolve() if cur else None

    # Cheap sort: oldest dir-mtime first. Deep checks (branch/idle/snapshot)
    # happen lazily only on the ones we actually try to remove.
    def _mtime(p: Path) -> float:
        try:
            return p.stat().st_mtime
        except OSError:
            return 0.0

    candidates = sorted(wts, key=_mtime)
    need = len(wts) - cap
    removed: list[str] = []
    skipped_active = 0

    for wt in candidates:
        if len(removed) >= need:
            break
        if cur_path and wt.resolve() == cur_path:
            continue
        if not _branch(wt).startswith("claude/"):
            continue  # never auto-remove a deliberate worktree
        if not is_idle(wt, idle_min=60):
            skipped_active += 1
            continue
        slug = wt.name
        snapped, _recoverable, all_safe = snapshot_unrecoverable(main_repo, wt, slug)
        if not all_safe:
            continue
        if remove_worktree(main_repo, wt, force=True):
            removed.append(slug)
            _log(main_repo, f"reclaimed {slug} (over cap {cap}, snapshotted {snapped} unsaved)")

    remaining = len(list_worktrees(main_repo))
    if not removed:
        if remaining > cap:
            return _emit(
                f"[worktree-cap] {remaining} worktrees (cap {cap}) but all over-cap ones are "
                f"active or deliberate — none safe to reclaim now. They'll be cleaned at their "
                f"SessionEnd, or run: python3 scripts/worktree-prune.sh"
            )
        return _emit(None)

    note = (f"[worktree-cap] Reclaimed {len(removed)} stale worktree(s) to stay under cap {cap} "
            f"(branches + any unsaved work preserved): {', '.join(removed[:8])}"
            + (f" +{len(removed) - 8} more" if len(removed) > 8 else "")
            + f". Now {remaining} worktree(s).")
    return _emit(note)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        print(json.dumps({"continue": True, "suppressOutput": True}))
        sys.exit(0)
