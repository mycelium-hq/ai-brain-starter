#!/usr/bin/env python3
"""snapshot-pending-work-on-stop must never write into the repo it snapshots.

The hook resolved its destination as `<main checkout>/⚙️ Meta/Worktree Snapshots`,
so in any PRODUCT repo with a `.claude/worktrees/` worktree it created `⚙️ Meta/`
at the repo root on every Stop: copies of unsaved code and docs, one `git add -A`
away from a commit. `_lib/worktree_safety.snapshot_dir_for` already answered
"where do snapshots go" correctly (the vault when identifiable, else
`~/.claude/worktree-snapshots`, never inside the reaped repo); this hook simply
did not call it.

Covered:
  1. product repo, no vault resolvable -> snapshot lands under $HOME/.claude,
     and nothing is created inside the repo.
  Negative control (run by hand when this was written): against the pre-fix hook
  the test fails on the `⚙️ Meta` assertion.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parent / "snapshot-pending-work-on-stop.py"


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


class SnapshotOutsideRepo(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.repo = self.tmp / "product"
        self.repo.mkdir()
        _git(self.repo, "init", "-q")
        _git(self.repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "init")
        self.wt = self.repo / ".claude" / "worktrees" / "feat"
        _git(self.repo, "worktree", "add", "-q", str(self.wt))
        (self.wt / "UNSAVED.md").write_text("pending work\n", encoding="utf-8")

    def _run(self) -> subprocess.CompletedProcess:
        env = {
            k: v
            for k, v in os.environ.items()
            if k not in {"VAULT_ROOT", "WORKTREE_ARTIFACT_ROOT", "SNAPSHOT_PENDING_BYPASS"}
        }
        env["HOME"] = str(self.home)
        env["CLAUDE_PROJECT_DIR"] = str(self.repo)
        return subprocess.run([sys.executable, str(HOOK)], cwd=self.wt, env=env, capture_output=True)

    def test_snapshot_lands_outside_the_repo(self) -> None:
        self.assertEqual(self._run().returncode, 0)
        self.assertFalse((self.repo / "⚙️ Meta").exists(), "hook wrote vault artifacts into the product repo")
        snap = self.home / ".claude" / "worktree-snapshots" / "feat" / "UNSAVED.md"
        self.assertTrue(snap.is_file(), "pending work was not snapshotted")


if __name__ == "__main__":
    unittest.main()
