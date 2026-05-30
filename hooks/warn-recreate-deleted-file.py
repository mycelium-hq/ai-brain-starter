#!/usr/bin/env python3
"""warn-recreate-deleted-file.py — Reliability Manifesto Pillar 6 enforcement.

PreToolUse(Write) hook. When the agent is about to Write a NEW file at a path
that a prior commit DELETED, warn: an intentional removal and an accidental loss
look identical from the outside and demand opposite responses. Read that
deletion commit before recreating the file.

WHY (Pillar 6 — verify external state before acting):
  An agent that sees a "missing" file and restores it can be undoing a
  deliberate cleanup. The git history is the deterministic source of truth for
  intent: if the last thing that happened to this path was a deletion, the agent
  must consult that commit (its message often says "remove X as stale/orphan")
  before recreating. This is the enforcement layer for the manifesto principle —
  high-precision because it checks git history, not model judgment.

SCOPE (deliberately narrow, to stay high-precision / low-false-positive):
  - Fires ONLY on Write (not Edit/MultiEdit — those target existing files).
  - Fires ONLY when the target path does NOT currently exist AND git history
    shows a commit that deleted exactly that path.
  - Overwriting a live file, creating a genuinely new file, or any path outside
    a git repo: silent.

WARN-ONLY. Never blocks. A false positive costs one informational line; a missed
intentional-delete-undo costs a silent regression (the asymmetry the manifesto
names). Bypass: RECREATE_DELETED_BYPASS=1.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def _emit(ctx: str | None) -> None:
    """PreToolUse contract: print JSON. additionalContext = inline warning."""
    if ctx:
        print(json.dumps({"continue": True, "additionalContext": ctx}))
    else:
        print(json.dumps({"continue": True, "suppressOutput": True}))


def _deletion_commit(repo: Path, rel: str) -> tuple[str, str] | None:
    """Return (sha, subject) of the most recent commit that DELETED `rel`, or None.

    Uses --diff-filter=D so only deletions count. Most-recent-first; we take the
    first hit. If a later commit re-added and re-deleted, the newest deletion is
    the relevant one — which is exactly what `log` returns first.
    """
    try:
        r = subprocess.run(
            ["git", "-C", str(repo), "log", "-1", "--diff-filter=D",
             "--format=%h\t%s", "--", rel],
            capture_output=True, text=True, timeout=10,
        )
    except (subprocess.SubprocessError, OSError):
        return None
    if r.returncode != 0:
        return None
    line = r.stdout.strip()
    if not line:
        return None
    sha, _, subject = line.partition("\t")
    return (sha, subject) if sha else None


def main() -> int:
    if os.environ.get("RECREATE_DELETED_BYPASS") == "1":
        _emit(None)
        return 0
    try:
        data = json.load(sys.stdin)
    except Exception:
        _emit(None)
        return 0

    if data.get("tool_name") != "Write":
        _emit(None)
        return 0

    file_path = (data.get("tool_input") or {}).get("file_path", "")
    if not file_path:
        _emit(None)
        return 0

    target = Path(file_path)
    # Only a genuine RE-creation: the path must not currently exist.
    if target.exists():
        _emit(None)
        return 0

    # Locate the enclosing git repo (the path itself doesn't exist, so walk parents).
    start = target.parent
    try:
        r = subprocess.run(
            ["git", "-C", str(start), "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=10,
        )
    except (subprocess.SubprocessError, OSError):
        _emit(None)
        return 0
    if r.returncode != 0:
        _emit(None)  # not in a git repo → no history to consult
        return 0
    repo = Path(r.stdout.strip())

    try:
        rel = str(target.resolve().relative_to(repo.resolve()))
    except ValueError:
        _emit(None)
        return 0

    hit = _deletion_commit(repo, rel)
    if not hit:
        _emit(None)  # never deleted in history → genuinely new, silent
        return 0

    sha, subject = hit
    _emit(
        f"[Pillar 6 — verify before recreate] You are about to Write `{rel}`, "
        f"but commit {sha} DELETED this exact path:\n"
        f"    {subject}\n"
        f"An intentional removal and an accidental loss look identical from here. "
        f"Read that commit first (`git -C {repo} show {sha}`) — if the deletion was "
        f"deliberate (cleanup/orphan/deprecation), recreating it re-introduces what "
        f"was removed on purpose; finish the cleanup instead. If it was accidental, "
        f"proceed. Bypass: RECREATE_DELETED_BYPASS=1."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
