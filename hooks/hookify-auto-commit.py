#!/usr/bin/env python3
"""PostToolUse hook: auto-commit hookify rule files the moment they're written.

Permanent-fix-pattern guard for the orphan-hookify-loss class:
- Hookify rule files (`.claude/hookify.*.local.md`) get created in worktrees.
- They sit untracked until session-close Phase 2b sweeps them.
- If the operator archives the worktree before that sweep runs (or if the
  file is created AFTER the sweep), the file is silently discarded by the
  archive's "discard uncommitted changes" path.
- This happened twice in the 2026-05-08 strange-sutherland session before
  the rule got codified; the lesson got captured in
  `hookify.warn-runtime-pro-cross-worktree.local.md` itself, which then
  almost-got-discarded on the very same archive prompt.

Fix: stage + commit hookify files the instant Edit / Write / MultiEdit
finishes. There's no untracked window for the archive prompt to catch.

Behavior:
- Match: file_path ends in `.claude/hookify.*.local.md`.
- Action: from the file's git toplevel, run
      git add <file>
      git commit -m "hookify: auto-stage <basename> drift"
  with GIT_VAULT_BYPASS=1 so the block-raw-vault-git PreToolUse guard
  doesn't fire on this internal write.
- Never block. Failures land in stderr + the hook log; the user's
  Edit/Write succeeds regardless.
- Idempotent: skips silently when the working tree shows no diff for
  the file (e.g. an Edit that produced no actual change).
- Per-file commit: many tiny commits is fine — hookify rules are rare
  enough that the noise is acceptable, and the alternative (batch at
  session-close) reintroduces the timing window we're trying to close.

Bypass: prefix the operator's edit with HOOKIFY_AUTO_COMMIT_BYPASS=1
in the environment (e.g. when actively iterating on a hookify rule
across many edits and you don't want a commit per keystroke). The hook
checks the env var per-call.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Shared stale-lock handler. Without this, a 0-byte index.lock from a crashed
# git operation makes our `git add` silently rc=128, the rc-check unstages and
# returns 0, and the auto-commit appears to succeed while doing nothing — the
# exact bug class fixed in reconcile-worktree-shared.py 2026-05-19.
sys.path.insert(0, str(Path(__file__).parent / "_lib"))
try:
    from git_safety import clear_stale_worktree_lock
except ImportError:
    def clear_stale_worktree_lock(_wt):  # type: ignore[no-redef]
        return True

LOG_FILE = Path.home() / ".claude" / "hooks" / "hookify-auto-commit.log"
HOOKIFY_PATTERN = re.compile(r"\.claude/hookify\..+\.local\.md$")


def log(msg: str) -> None:
    """Append one timestamped line to the hook log. Best-effort; never raise."""
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open("a", encoding="utf-8") as fh:
            fh.write(f"{datetime.now().isoformat(timespec='seconds')} {msg}\n")
    except OSError:
        pass


def main() -> int:
    if os.environ.get("HOOKIFY_AUTO_COMMIT_BYPASS") == "1":
        return 0

    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0  # No input, nothing to do.

    tool_input = payload.get("tool_input") or {}
    file_path = tool_input.get("file_path") or ""
    if not file_path:
        return 0
    if not HOOKIFY_PATTERN.search(file_path):
        return 0  # Not a hookify file; ignore.

    file_path_obj = Path(file_path)
    if not file_path_obj.exists():
        log(f"skip: hookify path does not exist on disk: {file_path}")
        return 0

    # Find the git toplevel for the file. Worktrees have their own toplevel
    # (separate working tree, shared .git/), so this lands the commit on
    # whatever branch the worktree is on rather than the main vault tree.
    repo_dir = file_path_obj.parent
    try:
        toplevel = subprocess.run(
            ["git", "-C", str(repo_dir), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        ).stdout.strip()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        log(f"skip: cannot find git toplevel for {file_path}: {exc}")
        return 0
    if not toplevel:
        log(f"skip: empty git toplevel for {file_path}")
        return 0

    # Vault-relative path the way git wants it.
    try:
        rel = str(file_path_obj.resolve().relative_to(Path(toplevel).resolve()))
    except ValueError:
        log(f"skip: {file_path} is not inside its own git toplevel {toplevel}")
        return 0

    # Bypass the block-raw-vault-git PreToolUse hook; we are the safe path.
    env = os.environ.copy()
    env["GIT_VAULT_BYPASS"] = "1"

    # Idempotency: if the file is already tracked AND has no diff, no commit
    # needed (an Edit that produced an identical write hits this).
    diff = subprocess.run(
        ["git", "-C", toplevel, "status", "--porcelain", "--", rel],
        capture_output=True,
        text=True,
        env=env,
        timeout=5,
    )
    porcelain = diff.stdout.strip()
    if not porcelain:
        return 0  # Nothing changed, nothing to commit.

    # Clear stale worktree index.lock before staging. If a real writer holds
    # the lock right now, skip this run rather than blocking the user's edit;
    # the next edit on this file will retry the full stage+commit cycle.
    if not clear_stale_worktree_lock(Path(toplevel)):
        log(f"skip: real git writer holds lock in {toplevel}, deferring {rel} to next edit")
        return 0

    add = subprocess.run(
        ["git", "-C", toplevel, "add", "--", rel],
        capture_output=True,
        text=True,
        env=env,
        timeout=10,
    )
    if add.returncode != 0:
        # `git add` failure shouldn't strand (it didn't reach the index),
        # but reset defensively in case partial staging occurred.
        subprocess.run(
            ["git", "-C", toplevel, "reset", "HEAD", "--", rel],
            capture_output=True,
            text=True,
            env=env,
            timeout=5,
        )
        log(
            f"git add failed for {rel} in {toplevel}: "
            f"rc={add.returncode} stderr={add.stderr.strip()[:200]}"
        )
        return 0

    basename = file_path_obj.stem
    msg = f"hookify: auto-stage {basename} drift\n\nPosted by hookify-auto-commit hook."
    commit = subprocess.run(
        ["git", "-C", toplevel, "commit", "-m", msg],
        capture_output=True,
        text=True,
        env=env,
        timeout=10,
    )
    if commit.returncode != 0:
        # Strand-prevention (matches auto-snapshot.sh v4 fix, 2026-05-14):
        # the file is currently staged. If we exit without unstaging it
        # stays in the index across sessions and creates a strand.
        # Reset HEAD on the path so it reverts to working-tree state.
        # Common reasons commit fails: pre-commit hook rejected, signing
        # key not available, transient lock contention. The next Edit/Write
        # on the file will retry the full stage+commit atomically.
        subprocess.run(
            ["git", "-C", toplevel, "reset", "HEAD", "--", rel],
            capture_output=True,
            text=True,
            env=env,
            timeout=5,
        )
        log(
            f"git commit failed for {rel} in {toplevel}: "
            f"rc={commit.returncode} stderr={commit.stderr.strip()[:200]} "
            f"(unstaged to prevent strand)"
        )
        return 0

    sha = subprocess.run(
        ["git", "-C", toplevel, "rev-parse", "--short", "HEAD"],
        capture_output=True, text=True, env=env, timeout=5,
    ).stdout.strip()
    log(f"committed {rel} as {sha} in {toplevel}")

    # Post-commit: FF active claude/* worktree branches to master so they
    # don't fall behind. Without this, every hookify auto-commit on main
    # leaves stale worktree branches that surface as false-positive
    # "uncommitted changes" at worktree-archive prompt. Closes the same
    # race vault-safe-commit.sh closes for its commits. Codified 2026-05-19
    # after 3 byte-identical hookify *.local.md files appeared as archive
    # warnings. Permanent-fix-pattern.
    #
    # Only meaningful when we just committed to the MAIN vault (not a
    # worktree). If toplevel IS a worktree, FF doesn't apply.
    if "/.claude/worktrees/" not in toplevel:
        try:
            worktrees = subprocess.run(
                ["git", "-C", toplevel, "worktree", "list", "--porcelain"],
                capture_output=True, text=True, env=env, timeout=5,
            ).stdout
            current_wt = None
            for line in worktrees.splitlines():
                if line.startswith("worktree "):
                    current_wt = line[len("worktree "):].strip()
                elif line.startswith("branch refs/heads/claude/") and current_wt:
                    if current_wt != toplevel:
                        subprocess.run(
                            ["git", "-C", current_wt, "merge",
                             "--ff-only", "--no-edit", "master"],
                            capture_output=True, env=env, timeout=10,
                        )
                    current_wt = None
        except (subprocess.TimeoutExpired, OSError) as exc:
            log(f"post-commit FF skipped: {exc}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
