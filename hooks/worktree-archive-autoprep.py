#!/usr/bin/env python3
"""Auto-prep worktree before Claude Code's archive prompt scans git status.

Permanent fix for the false-alarm archive warning that flagged 7+
hookify files as "permanent loss" when they were byte-identical to
main.

Mechanism: registered as a `Stop` hook in ~/.claude/settings.json.
Fires after every assistant turn. Detects whether the current working
directory is inside a vault worktree
(`<vault>/.claude/worktrees/<slug>/`); if so, invokes the existing
`worktree-archive-prep.py` script from the main vault path, which
removes byte-identical untracked duplicates and clears byte-identical
modified-file entries.

Idempotent — short-circuits silently when there's nothing to clean.
No-op when not in a worktree (most sessions).

Why a Stop hook (not SessionEnd):
- Stop fires on every assistant response, so the worktree stays
  clean continuously throughout the session.
- The archive prompt the harness shows when the user clicks
  "archive worktree" scans `git status` in real time. If we only
  cleaned at SessionEnd, there'd be a window where the user could
  click archive between turns and still see the false alarm.
- Stop fires often, so the script must short-circuit fast.
  worktree-archive-prep.py exits 0 silently when 0 untracked + 0
  modified, so the cost is one git status call per assistant turn.

Bypass: WORKTREE_AUTOPREP_BYPASS=1 in env if the prep itself misbehaves.

Codified 2026-05-09 after the false alarm fired across multiple
sessions despite Phase 2c (worktree-archive-prep) running at session
close. The Phase 2c run cleared the duplicates, then the worktree's
git status got recomputed (session resume / branch sync) and the same
false alarm re-fired. Stop-hook continuous cleanup closes that gap.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

# Where the prep script lives. Must be the MAIN vault path (the
# worktree filesystem won't have it under the same path because the
# worktree is a sparse checkout of the same git repo).
MAIN_VAULT = Path(os.environ.get("VAULT_ROOT", str(Path.home() / "vault")))
PREP_SCRIPT = MAIN_VAULT / "⚙️ Meta/scripts/worktree-archive-prep.py"


def main() -> int:
    if os.environ.get("WORKTREE_AUTOPREP_BYPASS") == "1":
        return 0

    cwd = Path.cwd().resolve()
    cwd_str = str(cwd)

    # Only run when actually inside a worktree.
    if "/.claude/worktrees/" not in cwd_str:
        return 0

    if not PREP_SCRIPT.exists():
        # Prep script missing — silent no-op. Don't break Stop hook
        # chain on a transient state.
        return 0

    # Run the prep script from the worktree cwd (it reads `git
    # status` from cwd to decide what to clean).
    # Use sys.executable (the python that launched this hook) instead of
    # bare "python3" so PATH shims (e.g. trailofbits/modern-python's
    # uv-nudge shim installed 2026-05-09) don't silently 1-out the call.
    try:
        result = subprocess.run(
            [sys.executable, str(PREP_SCRIPT)],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        # Hook never blocks the assistant turn. Silent on transient
        # failure; the next Stop fires fresh.
        return 0

    # Surface output ONLY when the prep actually did something
    # (exit 0 + non-empty stdout). Silent otherwise so the hook
    # doesn't fill the transcript with no-op messages.
    if result.returncode == 0 and result.stdout.strip():
        # Send to stderr so it shows in the harness log without
        # polluting the conversation transcript.
        print(
            f"[worktree-archive-autoprep] {result.stdout.strip()}",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
