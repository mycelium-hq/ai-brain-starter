#!/usr/bin/env python3
"""Negative control: a script that stages ITS OWN paths must commit ONLY those paths.

The bug class: stage own paths, then run a bare `git commit -m`. A bare commit takes the
WHOLE index, so a file another session had staged in the same checkout rides along into the
automated commit. Measured 2026-10-18: a vault sync script swept 7 unrelated staged files,
one an unreviewed 700-line script change, into an automated commit.

Drives the REAL code against throwaway git repos that hold an unrelated staged file:
  * hooks/hookify-auto-commit.py        -- the per-file commit right after a hookify rule is written
  * hooks/reconcile-worktree-shared.py  -- the fallback commit when the fast-forward is impossible
  * scripts/vault-daily-maintenance.sh  -- the reconcile-commit block, lifted verbatim out of the
                                           shipped script (the pass around it needs a load gate, a
                                           mutex and the aggregators); the lift is asserted, so a
                                           moved block fails loudly instead of testing nothing

Mutant this kills: the bare commit. Drop the trailing `"--", rel` from hookify-auto-commit.py's
commit, `"--", *reconciled` from reconcile-worktree-shared.py's fallback commit, or the
`-- "${STAGED[@]}"` from the maintenance block, and the matching test goes red. A control test
proves the sandbox is honest: a bare commit in the same kind of fixture really does sweep the
foreign file in, so "it stayed staged" cannot pass because git scoped the commit by itself.

The maintenance legs also pin three things the naive `git commit -- "${PATHS[@]}"` gets wrong:
an empty Decisions/ directory (git aborts: "pathspec did not match any file(s) known to git"),
a rename (without --no-renames the old path's deletion is left staged), and a vault that lives
in a subdirectory of its repo (without --relative the staged names do not resolve from there).

Run: python3 hooks/test_commit_only_own_paths.py
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOKS = Path(__file__).resolve().parent
HOOKIFY_AUTO_COMMIT = HOOKS / "hookify-auto-commit.py"
RECONCILE = HOOKS / "reconcile-worktree-shared.py"
MAINTENANCE = HOOKS.parent / "scripts" / "vault-daily-maintenance.sh"
BASH = "/bin/bash" if os.path.exists("/bin/bash") else "bash"  # macOS /bin/bash is 3.2: the portability floor

# The git-LOCATION family would point git at the caller's repo instead of the fixture.
_DROP = {
    "GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_NAMESPACE", "GIT_CEILING_DIRECTORIES",
    "GIT_DISCOVERY_ACROSS_FILESYSTEM", "GIT_PREFIX", "CDPATH",
}


def _clean_env(home: Path) -> dict:
    """Sandboxed HOME (+ USERPROFILE for Windows), no global/system git config, fixed identity."""
    env = {k: v for k, v in os.environ.items() if k not in _DROP and not k.startswith("GIT_CONFIG")}
    env.update({
        "HOME": str(home),
        "USERPROFILE": str(home),
        "XDG_CONFIG_HOME": str(home / ".config"),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid",
    })
    return env


def _git(cwd: Path, env: dict, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=str(cwd), env=env, check=True,
        capture_output=True, text=True, encoding="utf-8",
    ).stdout


def _names(out: str) -> list:
    return sorted(line for line in out.splitlines() if line)


def _lift_reconcile_commit_block() -> str:
    """The shipped `if ...; then ... fi` that commits deferred close artifacts, verbatim."""
    src = MAINTENANCE.read_text(encoding="utf-8")
    m = re.search(
        r'^if \[ -d "\$VAULT/\.git" \] \|\| git -C "\$VAULT" rev-parse --git-dir[^\n]*\n.*?^fi$',
        src, re.S | re.M,
    )
    if m is None or "PATHS=()" not in m.group(0) or "git commit" not in m.group(0):
        raise AssertionError(
            "could not lift the reconcile-commit block out of scripts/vault-daily-maintenance.sh -- "
            "it moved or was renamed, so the maintenance legs below would test nothing. "
            "Fix the extraction, not the assertion."
        )
    return m.group(0)


class CommitOnlyOwnPaths(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="cop-")).resolve()
        self.addCleanup(shutil.rmtree, str(self.tmp), True)
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.env = _clean_env(self.home)

    def _init_repo(self, name: str) -> Path:
        repo = self.tmp / name
        repo.mkdir()
        _git(repo, self.env, "init", "-q")
        _git(repo, self.env, "symbolic-ref", "HEAD", "refs/heads/main")
        _git(repo, self.env, "config", "commit.gpgsign", "false")
        return repo

    def _commit_file(self, repo: Path, rel: str, text: str, msg: str) -> None:
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        _git(repo, self.env, "add", "--", rel)
        _git(repo, self.env, "commit", "-q", "-m", msg)

    def _stage_foreign(self, repo: Path) -> None:
        (repo / "someone-elses-wip.sh").write_text("staged by another session\n", encoding="utf-8")
        _git(repo, self.env, "add", "--", "someone-elses-wip.sh")
        self.assertEqual(_names(_git(repo, self.env, "diff", "--cached", "--name-only")),
                         ["someone-elses-wip.sh"], "fixture: the foreign file must start out staged")

    def _run_maintenance_block(self, vault: Path, meta: Path) -> None:
        harness = self.tmp / "maintenance-harness.sh"
        harness.write_text(
            "set +e\n"
            'VAULT="$1"; META_DIR="$2"; LOG="$3"\n'
            "log() { :; }\n"
            "vault_git_wait_unlocked() { return 0; }\n"
            + _lift_reconcile_commit_block() + "\n",
            encoding="utf-8",
        )
        subprocess.run(
            [BASH, str(harness), str(vault), str(meta), str(self.tmp / "maintenance.log")],
            env=self.env, check=True, capture_output=True, text=True, encoding="utf-8",
        )

    def test_control_a_bare_commit_sweeps_the_whole_index(self) -> None:
        repo = self._init_repo("control")
        self._commit_file(repo, "base.txt", "base\n", "base")
        (repo / "mine.txt").write_text("mine\n", encoding="utf-8")
        (repo / "theirs.sh").write_text("theirs\n", encoding="utf-8")
        _git(repo, self.env, "add", "--", "mine.txt", "theirs.sh")
        _git(repo, self.env, "commit", "-q", "-m", "bare")
        self.assertEqual(_names(_git(repo, self.env, "show", "--name-only", "--format=", "HEAD")),
                         ["mine.txt", "theirs.sh"])

    def test_hookify_auto_commit_leaves_a_foreign_staged_file_staged(self) -> None:
        repo = self._init_repo("hookify")
        self._commit_file(repo, "README.md", "base\n", "base")
        rule = repo / ".claude" / "hookify.demo.local.md"
        rule.parent.mkdir()
        rule.write_text("a new hookify rule\n", encoding="utf-8")
        self._stage_foreign(repo)

        r = subprocess.run(
            [sys.executable, str(HOOKIFY_AUTO_COMMIT)],
            input=json.dumps({"tool_input": {"file_path": str(rule)}}),
            cwd=str(repo), env=self.env, capture_output=True, text=True, encoding="utf-8",
        )

        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(_git(repo, self.env, "log", "-1", "--format=%s").strip(),
                         "hookify: auto-stage hookify.demo.local drift",
                         "the hook did not commit the rule, so the checks below would prove nothing")
        self.assertEqual(_names(_git(repo, self.env, "show", "--name-only", "--format=", "HEAD")),
                         [".claude/hookify.demo.local.md"])
        self.assertEqual(_names(_git(repo, self.env, "diff", "--cached", "--name-only")),
                         ["someone-elses-wip.sh"])

    def test_reconcile_fallback_commit_leaves_a_foreign_staged_file_staged(self) -> None:
        vault = self._init_repo("vault")
        rule_rel = ".claude/hookify.demo.local.md"
        self._commit_file(vault, rule_rel, "rule v1\n", "base")
        wt = vault / ".claude" / "worktrees" / "slug"
        _git(vault, self.env, "worktree", "add", "-q", "-b", "claude/slug", str(wt), "main")
        # Diverge the two branches so the fast-forward the hook tries first is impossible.
        self._commit_file(vault, "main-only.txt", "main moves on\n", "main moves on")
        self._commit_file(wt, "branch-only.txt", "branch moves on\n", "branch moves on")
        # The rule is rewritten at the main vault and mirrored byte-for-byte into the worktree.
        (vault / rule_rel).write_text("rule v2\n", encoding="utf-8")
        (wt / rule_rel).write_text("rule v2\n", encoding="utf-8")
        self._stage_foreign(wt)

        r = subprocess.run(
            [sys.executable, str(RECONCILE)],
            cwd=str(wt), env=self.env, stdin=subprocess.DEVNULL,
            capture_output=True, text=True, encoding="utf-8",
        )

        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("not possible", r.stdout, "the fast-forward unexpectedly worked, so the commit path never ran")
        self.assertIn("committed 1 file(s)", r.stdout)
        self.assertTrue(_git(wt, self.env, "log", "-1", "--format=%s").startswith("auto: reconcile-worktree-shared synced 1"))
        self.assertEqual(_names(_git(wt, self.env, "show", "--name-only", "--format=", "HEAD")), [rule_rel])
        self.assertEqual(_names(_git(wt, self.env, "diff", "--cached", "--name-only")),
                         ["someone-elses-wip.sh"])

    def test_maintenance_reconcile_commit_takes_only_the_close_artifacts(self) -> None:
        for layout, sub in (("vault at the repo root", ""), ("vault in a subdirectory of its repo", "sub/")):
            with self.subTest(layout=layout):
                repo = self._init_repo("maint-sub" if sub else "maint-root")
                vault = repo / sub.rstrip("/") if sub else repo
                self._commit_file(repo, sub + "Meta/Sessions/old.md", "old\n", "base")
                self._commit_file(repo, sub + "Meta/Sessions/from.md", "same body\n", "more")
                self._commit_file(repo, sub + "Meta/Last Session.md", "v1\n", "more")
                meta = vault / "Meta"
                (meta / "Sessions" / "old.md").unlink()                                # a deletion
                (meta / "Sessions" / "from.md").rename(meta / "Sessions" / "to.md")    # a rename
                (meta / "Sessions" / "new.md").write_text("new\n", encoding="utf-8")    # a new file
                (meta / "Decisions").mkdir()                                            # nothing tracked here yet
                (meta / "Last Session.md").write_text("v2\n", encoding="utf-8")         # a modification
                self._stage_foreign(repo)

                self._run_maintenance_block(vault, meta)

                self.assertTrue(
                    _git(repo, self.env, "log", "-1", "--format=%s").startswith("maint: reconcile deferred session-close"),
                    "the block did not commit, so the checks below would prove nothing",
                )
                self.assertEqual(
                    _names(_git(repo, self.env, "show", "--no-renames", "--name-only", "--format=", "HEAD")),
                    sorted(sub + p for p in (
                        "Meta/Sessions/old.md", "Meta/Sessions/from.md", "Meta/Sessions/to.md",
                        "Meta/Sessions/new.md", "Meta/Last Session.md",
                    )),
                )
                self.assertEqual(_names(_git(repo, self.env, "diff", "--cached", "--name-only")),
                                 ["someone-elses-wip.sh"])
                self.assertEqual(_git(repo, self.env, "status", "--porcelain", "--", sub + "Meta"), "",
                                 "a close artifact was left uncommitted or staged")

    def test_maintenance_reconcile_commit_is_a_noop_when_only_a_foreign_file_is_staged(self) -> None:
        repo = self._init_repo("maint-noop")
        self._commit_file(repo, "Meta/Sessions/s.md", "s\n", "base")
        self._stage_foreign(repo)
        head = _git(repo, self.env, "rev-parse", "HEAD")

        self._run_maintenance_block(repo, repo / "Meta")

        self.assertEqual(_git(repo, self.env, "rev-parse", "HEAD"), head,
                         "a foreign staged file was committed under the maintenance message")
        self.assertEqual(_names(_git(repo, self.env, "diff", "--cached", "--name-only")),
                         ["someone-elses-wip.sh"])


if __name__ == "__main__":
    unittest.main()
