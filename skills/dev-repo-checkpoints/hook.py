#!/usr/bin/env python3
"""Auto-checkpoint hook for ~/dev/* code repos.

Stop / SubagentStop event: when the current session's cwd is under
~/dev/<repo>, stash the working tree as a recoverable checkpoint without
modifying state. Closes the gap where long Claude Code sessions in code
repos can lose uncommitted work on branch switches when vault-level
snapshot scripts do not cover ~/dev/*.

Recover any checkpoint via `git stash list | grep claude-checkpoint` then
`git stash apply stash@{N}` to keep it, or `git stash pop` to drop on apply.

Pattern source: carlrannaberg/claudekit MIT
(cli/hooks/create-checkpoint.ts). Reimplemented clean in Python.

Install:
1. Drop this file at ~/.claude/hooks/create-dev-repo-checkpoint.py
2. `chmod +x ~/.claude/hooks/create-dev-repo-checkpoint.py`
3. Register in ~/.claude/settings.json under Stop AND SubagentStop:
     {"type": "command",
      "command": "/usr/bin/python3 /Users/<you>/.claude/hooks/create-dev-repo-checkpoint.py 2>/dev/null || true"}

Customize:
- DEV_ROOT: change if your code repos live somewhere other than ~/dev/
- VAULT_ROOT: set to your second-brain / notes-vault path so the hook
  never tries to `git add -A` in a 60K-file markdown vault. Leave as None
  if you do not have one, or if it already lives outside ~/dev/.

Bypass: DEV_CHECKPOINT_BYPASS=1
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

BYPASS_ENV = "DEV_CHECKPOINT_BYPASS"
PREFIX = "claude-checkpoint"
MAX_CHECKPOINTS = 20
DEV_ROOT = Path.home() / "dev"

# Set this to your local notes-vault path if you have one, so the hook
# never tries to `git add -A` in a large markdown vault. Leave as None if
# you do not have a separate vault or if your vault already lives outside
# DEV_ROOT. Example: `Path.home() / "Documents" / "my-notes"`.
VAULT_ROOT: Optional[Path] = None


def run_git(repo: Path, args: list[str], timeout: int = 10) -> subprocess.CompletedProcess:
    """Run `git -C <repo> <args>` with bounded timeout. Never raises."""
    try:
        return subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return subprocess.CompletedProcess(args, returncode=1, stdout="", stderr="")


def is_git_repo(path: Path) -> Optional[Path]:
    res = run_git(path, ["rev-parse", "--show-toplevel"], timeout=5)
    if res.returncode != 0:
        return None
    return Path(res.stdout.strip())


def has_changes(repo: Path) -> bool:
    res = run_git(repo, ["status", "--porcelain"])
    return res.returncode == 0 and bool(res.stdout.strip())


def checkpoint(repo: Path, message: str) -> bool:
    add = run_git(repo, ["add", "-A"], timeout=30)
    if add.returncode != 0:
        return False

    create = run_git(repo, ["stash", "create", message], timeout=30)
    sha = create.stdout.strip()
    if create.returncode != 0 or not sha:
        run_git(repo, ["reset"])
        return False

    store = run_git(repo, ["stash", "store", "-m", message, sha])
    if store.returncode != 0:
        run_git(repo, ["reset"])
        return False

    run_git(repo, ["reset"])
    return True


def rotate_checkpoints(repo: Path, max_count: int) -> None:
    res = run_git(repo, ["stash", "list"])
    if res.returncode != 0:
        return

    ours_indices: list[int] = []
    for i, line in enumerate(res.stdout.splitlines()):
        if PREFIX in line:
            ours_indices.append(i)

    to_drop = ours_indices[max_count:]
    for idx in sorted(to_drop, reverse=True):
        run_git(repo, ["stash", "drop", f"stash@{{{idx}}}"])


def main() -> int:
    if os.environ.get(BYPASS_ENV) == "1":
        return 0

    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        payload = {}

    cwd_str = payload.get("cwd") or os.environ.get("PWD") or os.getcwd()
    try:
        cwd = Path(cwd_str).resolve()
    except (OSError, RuntimeError):
        return 0

    # Skip the vault if configured (covered by separate snapshot script)
    if VAULT_ROOT is not None:
        try:
            cwd.relative_to(VAULT_ROOT.resolve())
            return 0
        except ValueError:
            pass

    # Only fire under ~/dev/<repo>
    try:
        cwd.relative_to(DEV_ROOT.resolve())
    except ValueError:
        return 0

    repo = is_git_repo(cwd)
    if repo is None:
        return 0

    # Defense-in-depth: confirm resolved repo is still under DEV_ROOT
    try:
        repo.resolve().relative_to(DEV_ROOT.resolve())
    except ValueError:
        return 0

    if not has_changes(repo):
        return 0

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    message = f"{PREFIX}: {timestamp} ({repo.name})"

    ok = checkpoint(repo, message)
    if ok:
        rotate_checkpoints(repo, MAX_CHECKPOINTS)

    return 0


if __name__ == "__main__":
    sys.exit(main())
